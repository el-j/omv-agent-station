<?php
/**
 * PHPUnit coverage for openmediavault-agent-station's AgentStation RPC
 * service (issue #21: agentstation.inc had zero tests -- this is how the
 * installClaudeCli unregistered-method bug fixed in PR #11 went
 * unnoticed).
 */

use OMV\Engined\Rpc\AgentStation;
use OMV\System\Process;
use PHPUnit\Framework\TestCase;

final class AgentStationTest extends TestCase
{
    private string $configPath;
    private string $dataDir;
    private string $cliPath;
    private array $context;

    protected function setUp(): void
    {
        $this->configPath = sys_get_temp_dir() . "/agentstation_test_config_" . uniqid() . ".json";
        putenv("AGENTSTATION_TEST_CONFIG_PATH=" . $this->configPath);

        $this->dataDir = sys_get_temp_dir() . "/agentstation_test_data_" . uniqid();
        mkdir($this->dataDir, 0755, true);
        // Keeps the persistent-storage fallback inside the temp tree: the real
        // /srv/dev-data exists and is root-owned on a developer box, so the
        // fallback read would warn with "Permission denied".
        putenv("AGENTSTATION_TEST_DATA_DIR=" . $this->dataDir);

        // Points at a path that deliberately does NOT exist, so each test
        // starts in the "CLI helper not installed" state and opts in to the
        // installed state via installCliHelper().
        $this->cliPath = $this->dataDir . "/omv-agent-station";
        putenv("AGENTSTATION_TEST_CLI_PATH=" . $this->cliPath);

        Process::reset();

        $this->context = ["username" => "admin", "role" => OMV_ROLE_ADMINISTRATOR];
    }

    protected function tearDown(): void
    {
        putenv("AGENTSTATION_TEST_CONFIG_PATH");
        putenv("AGENTSTATION_TEST_CLI_PATH");
        putenv("AGENTSTATION_TEST_DATA_DIR");
        Process::reset();
        @unlink($this->configPath);
        $this->rrmdir($this->dataDir);
    }

    /** Makes file_exists($this->getCliPath()) true, as on a real install. */
    private function installCliHelper(): void
    {
        file_put_contents($this->cliPath, "#!/bin/sh\nexit 0\n");
    }

    /** @param array<int, string> $lines */
    private function cannedOutput(string $commandLine, array $lines): void
    {
        Process::$responses[$commandLine] = $lines;
    }

    /** @return array<int, string> The full command lines the stub was asked to run. */
    private function executedCommands(): array
    {
        return array_map(fn ($argv) => implode(" ", $argv), Process::$log);
    }

    private function rrmdir(string $dir): void
    {
        if (!is_dir($dir)) {
            return;
        }
        foreach (scandir($dir) as $entry) {
            if ($entry === "." || $entry === "..") {
                continue;
            }
            $path = "$dir/$entry";
            is_dir($path) ? $this->rrmdir($path) : unlink($path);
        }
        rmdir($dir);
    }

    private function newService(): AgentStation
    {
        $service = new AgentStation();
        $service->initialize();
        return $service;
    }

    // -------------------------------------------------------------------
    // Complements tests/test_omv_rpc_registration.py, which only checks
    // "every public method is registered". This checks the reverse: every
    // registered RPC name actually resolves to a callable method -- the
    // exact shape of bug PR #11 fixed for installClaudeCli.
    // -------------------------------------------------------------------

    public function testEveryRegisteredMethodIsReachable(): void
    {
        $service = $this->newService();
        $names = $service->getRegisteredMethodNames();

        $this->assertNotEmpty($names, "AgentStation registered zero RPC methods");
        foreach ($names as $name) {
            $this->assertTrue($service->hasMethod($name), "Registered method '$name' is not reachable via hasMethod()");
        }
    }

    // -------------------------------------------------------------------
    // setSettings: secret-preservation-on-partial-save
    // -------------------------------------------------------------------

    public function testSetSettingsPreservesSecretWhenPartialSaveSubmitsItEmpty(): void
    {
        $service = $this->newService();

        $service->callMethod("setSettings", [
            "data_dir" => $this->dataDir,
            "gemini_api_key" => "real-secret-key",
        ], $this->context);

        // A later save from a different tab of the form, where the secret
        // field wasn't touched and Angular submits it as "".
        $result = $service->callMethod("setSettings", [
            "data_dir" => $this->dataDir,
            "gemini_api_key" => "",
        ], $this->context);

        $this->assertSame("real-secret-key", $result["gemini_api_key"]);
    }

    public function testSetSettingsOverwritesSecretWhenNonEmptyValueSubmitted(): void
    {
        $service = $this->newService();

        $service->callMethod("setSettings", [
            "data_dir" => $this->dataDir,
            "gemini_api_key" => "old-key",
        ], $this->context);

        $result = $service->callMethod("setSettings", [
            "data_dir" => $this->dataDir,
            "gemini_api_key" => "new-key",
        ], $this->context);

        $this->assertSame("new-key", $result["gemini_api_key"]);
    }

    public function testSetSettingsCoercesBooleanFieldsFromFormlyStrings(): void
    {
        $service = $this->newService();

        $result = $service->callMethod("setSettings", [
            "data_dir" => $this->dataDir,
            "enable" => "true",
            "enable_git" => "0",
        ], $this->context);

        $this->assertTrue($result["enable"]);
        $this->assertFalse($result["enable_git"]);
    }

    public function testSetSettingsPersistsToPrimaryAndDataDirBackup(): void
    {
        $service = $this->newService();
        $service->callMethod("setSettings", [
            "data_dir" => $this->dataDir,
            "enable" => "true",
        ], $this->context);

        $this->assertFileExists($this->configPath);
        $this->assertFileExists($this->dataDir . "/config/agent-station.json");

        $primary = json_decode(file_get_contents($this->configPath), true);
        $backup = json_decode(file_get_contents($this->dataDir . "/config/agent-station.json"), true);
        $this->assertTrue($primary["enable"]);
        $this->assertTrue($backup["enable"]);
    }

    // -------------------------------------------------------------------
    // getStatus: status derivation (issue #18's "Stopped"/"Provisioning"
    // baseline this builds on -- the crashed-vs-provisioning split itself
    // lives in the CLI script and is covered by
    // tests/test_container_status.py, since /usr/sbin/omv-agent-station
    // isn't present in this test environment)
    // -------------------------------------------------------------------

    public function testGetStatusReportsStoppedWhenDisabled(): void
    {
        $service = $this->newService();
        $service->callMethod("setSettings", [
            "data_dir" => $this->dataDir,
            "enable" => "false",
        ], $this->context);

        $rows = $service->callMethod("getStatus", [], $this->context);
        $engine = $this->findRow($rows, "Engine");

        $this->assertFalse($engine["enabled"]);
        $this->assertFalse($engine["crashed"]);
        $this->assertSame("Stopped", $engine["detail"]);
    }

    public function testGetStatusReportsProvisioningWhenEnabledWithNoContainerYet(): void
    {
        $service = $this->newService();
        $service->callMethod("setSettings", [
            "data_dir" => $this->dataDir,
            "enable" => "true",
        ], $this->context);

        $rows = $service->callMethod("getStatus", [], $this->context);
        $engine = $this->findRow($rows, "Engine");

        // The CLI helper isn't installed in this test environment, so
        // getPerformance() reports no running containers -- "enabled but
        // nothing up yet" must read as provisioning, not crashed.
        $this->assertFalse($engine["enabled"]);
        $this->assertFalse($engine["crashed"]);
        $this->assertStringContainsString("Provisioning", $engine["detail"]);
    }

    public function testGetStatusAiModelsRowReflectsConfiguredKeys(): void
    {
        $service = $this->newService();
        $service->callMethod("setSettings", [
            "data_dir" => $this->dataDir,
            "gemini_api_key" => "a-key",
        ], $this->context);

        $rows = $service->callMethod("getStatus", [], $this->context);
        $aiModels = $this->findRow($rows, "AI Models");

        $this->assertSame("Keys configured", $aiModels["detail"]);
    }

    private function findRow(array $rows, string $name): array
    {
        foreach ($rows as $row) {
            if ($row["name"] === $name) {
                return $row;
            }
        }
        $this->fail("No '$name' row in getStatus() output");
    }

    // -------------------------------------------------------------------
    // Authorization
    // -------------------------------------------------------------------

    public function testMethodsRejectNonAdminContext(): void
    {
        $service = $this->newService();
        $this->expectException(\OMV\Rpc\Exception::class);
        $service->callMethod("getSettings", [], ["username" => "guest", "role" => 0]);
    }

    /**
     * Issue #54: 7 of the 10 registered RPC methods had no method-specific
     * assertion at all. Every one of them is reachable from the Workbench UI,
     * so a silent breakage in any of them is a broken button for the user.
     */
    #[PHPUnit\Framework\Attributes\DataProvider("previouslyUncoveredMethodProvider")]
    public function testEveryMethodRejectsNonAdminContext(string $method, array $params): void
    {
        $service = $this->newService();
        $this->expectException(\OMV\Rpc\Exception::class);
        $service->callMethod($method, $params, ["username" => "guest", "role" => 0]);
    }

    public static function previouslyUncoveredMethodProvider(): array
    {
        return [
            "getDiagnostics" => ["getDiagnostics", []],
            "getPerformance" => ["getPerformance", []],
            "restartServices" => ["restartServices", []],
            "getLogs" => ["getLogs", []],
            "installClaudeCli" => ["installClaudeCli", []],
            "checkForUpdate" => ["checkForUpdate", []],
            "updatePlugin" => ["updatePlugin", []],
        ];
    }

    // -------------------------------------------------------------------
    // getPerformance
    // -------------------------------------------------------------------

    public function testGetPerformanceReturnsEmptyArrayWithoutCliHelper(): void
    {
        $service = $this->newService();
        $this->assertSame([], $service->callMethod("getPerformance", [], $this->context));
        $this->assertSame([], Process::$log, "No subprocess should be spawned when the helper is absent");
    }

    public function testGetPerformanceDecodesCliJson(): void
    {
        $this->installCliHelper();
        $this->cannedOutput("omv-agent-station performance", [
            '{"containers":{"LiteLLM Gateway":true},',
            '"container_details":{"LiteLLM Gateway":{"state":"running","status":"Up 3 minutes"}}}',
        ]);

        $service = $this->newService();
        $perf = $service->callMethod("getPerformance", [], $this->context);

        $this->assertTrue($perf["containers"]["LiteLLM Gateway"]);
        $this->assertSame("Up 3 minutes", $perf["container_details"]["LiteLLM Gateway"]["status"]);
        $this->assertContains("omv-agent-station performance", $this->executedCommands());
    }

    public function testGetPerformanceReturnsEmptyArrayOnMalformedJson(): void
    {
        $this->installCliHelper();
        $this->cannedOutput("omv-agent-station performance", ["{not valid json"]);

        $service = $this->newService();
        // Must degrade to [] rather than throwing -- getStatus() and
        // getDiagnostics() both call straight through this.
        $this->assertSame([], $service->callMethod("getPerformance", [], $this->context));
    }

    public function testGetPerformanceReturnsEmptyArrayOnEmptyCliOutput(): void
    {
        $this->installCliHelper();
        $service = $this->newService();
        $this->assertSame([], $service->callMethod("getPerformance", [], $this->context));
    }

    // -------------------------------------------------------------------
    // getStatus, driven by real getPerformance output
    // -------------------------------------------------------------------

    public function testGetStatusReportsActiveWhenAContainerIsRunning(): void
    {
        $this->installCliHelper();
        $this->cannedOutput("omv-agent-station performance", [
            '{"containers":{"LiteLLM Gateway":true},"container_details":{"LiteLLM Gateway":{"state":"running"}}}',
        ]);

        $service = $this->newService();
        $service->callMethod("setSettings", ["data_dir" => $this->dataDir, "enable" => "true"], $this->context);

        $engine = $this->findRow($service->callMethod("getStatus", [], $this->context), "Engine");
        $this->assertTrue($engine["enabled"]);
        $this->assertFalse($engine["crashed"]);
        $this->assertStringContainsString("Active", $engine["detail"]);
    }

    public function testGetStatusReportsCrashedWhenAContainerExitedWithError(): void
    {
        $this->installCliHelper();
        $this->cannedOutput("omv-agent-station performance", [
            '{"containers":{"LiteLLM Gateway":false},"container_details":{"LiteLLM Gateway":{"state":"exited_error"}}}',
        ]);

        $service = $this->newService();
        $service->callMethod("setSettings", ["data_dir" => $this->dataDir, "enable" => "true"], $this->context);

        $engine = $this->findRow($service->callMethod("getStatus", [], $this->context), "Engine");
        $this->assertTrue($engine["crashed"]);
        $this->assertStringContainsString("Crashed", $engine["detail"]);
    }

    // -------------------------------------------------------------------
    // getDiagnostics
    // -------------------------------------------------------------------

    public function testGetDiagnosticsReturnsAllPanelKeys(): void
    {
        $service = $this->newService();
        $service->callMethod("setSettings", ["data_dir" => $this->dataDir], $this->context);

        $diag = $service->callMethod("getDiagnostics", [], $this->context);

        foreach (["container_status", "storage_status", "ai_status", "update_status", "log_output"] as $key) {
            $this->assertArrayHasKey($key, $diag);
            $this->assertIsString($diag[$key]);
        }
    }

    public function testGetDiagnosticsListsEveryKnownContainerAsStoppedWithoutCliHelper(): void
    {
        $service = $this->newService();
        $service->callMethod("setSettings", ["data_dir" => $this->dataDir], $this->context);

        $diag = $service->callMethod("getDiagnostics", [], $this->context);

        foreach (["LiteLLM Gateway", "Web Terminal", "Syncthing", "Telegram Bot"] as $name) {
            $this->assertStringContainsString($name, $diag["container_status"]);
        }
        $this->assertStringContainsString("Stopped", $diag["container_status"]);
    }

    public function testGetDiagnosticsReflectsLiveContainerStatuses(): void
    {
        $this->installCliHelper();
        $this->cannedOutput("omv-agent-station performance", [
            '{"container_details":{"Syncthing":{"state":"running","status":"Up 2 hours (healthy)"}}}',
        ]);

        $service = $this->newService();
        $service->callMethod("setSettings", ["data_dir" => $this->dataDir], $this->context);

        $diag = $service->callMethod("getDiagnostics", [], $this->context);
        $this->assertStringContainsString("Up 2 hours (healthy)", $diag["container_status"]);
    }

    public function testGetDiagnosticsFallsBackWhenNoLogsRecorded(): void
    {
        $service = $this->newService();
        $service->callMethod("setSettings", ["data_dir" => $this->dataDir], $this->context);

        $diag = $service->callMethod("getDiagnostics", [], $this->context);
        $this->assertStringContainsString("No startup logs recorded yet", $diag["log_output"]);
    }

    public function testGetDiagnosticsStripsAnsiEscapesAndBlankLinesFromLogs(): void
    {
        $this->installCliHelper();
        $this->cannedOutput("omv-agent-station logs all", [
            "\x1B[32mlitellm  |\x1B[0m Application startup complete.",
            "   ",
            "syncthing | Ready to synchronize",
        ]);

        $service = $this->newService();
        $service->callMethod("setSettings", ["data_dir" => $this->dataDir], $this->context);

        $diag = $service->callMethod("getDiagnostics", [], $this->context);
        $this->assertStringNotContainsString("\x1B[", $diag["log_output"]);
        $this->assertStringContainsString("Application startup complete.", $diag["log_output"]);
        $this->assertSame(2, substr_count($diag["log_output"], "\n") + 1, "The blank line should have been dropped");
    }

    public function testGetDiagnosticsReportsConfiguredAiProviders(): void
    {
        $service = $this->newService();
        $service->callMethod("setSettings", [
            "data_dir" => $this->dataDir,
            "gemini_api_key" => "g-key",
            "mistral_api_key" => "",
        ], $this->context);

        $diag = $service->callMethod("getDiagnostics", [], $this->context);
        $this->assertMatchesRegularExpression('/Google Gemini Studio\s*: ✅/u', $diag["ai_status"]);
        $this->assertMatchesRegularExpression('/Mistral AI Direct\s*: ⚪/u', $diag["ai_status"]);
    }

    public function testGetDiagnosticsReportsStorageDirectoriesFromSettings(): void
    {
        $service = $this->newService();
        $service->callMethod("setSettings", ["data_dir" => $this->dataDir], $this->context);
        mkdir($this->dataDir . "/workspace", 0755, true);

        $diag = $service->callMethod("getDiagnostics", [], $this->context);
        $this->assertStringContainsString($this->dataDir . "/workspace", $diag["storage_status"]);
        $this->assertStringContainsString($this->dataDir . "/obsidian", $diag["storage_status"]);
    }

    public function testGetDiagnosticsSurfacesUpdateCheckErrorWithoutCliHelper(): void
    {
        $service = $this->newService();
        $service->callMethod("setSettings", ["data_dir" => $this->dataDir], $this->context);

        $diag = $service->callMethod("getDiagnostics", [], $this->context);
        $this->assertStringContainsString("CLI helper not found", $diag["update_status"]);
    }

    public function testGetDiagnosticsAnnouncesAvailableUpdate(): void
    {
        $this->installCliHelper();
        $this->cannedOutput("omv-agent-station check-update", [
            '{"current_version":"0.0.2","latest_version":"0.0.3","update_available":true}',
        ]);

        $service = $this->newService();
        $service->callMethod("setSettings", ["data_dir" => $this->dataDir], $this->context);

        $diag = $service->callMethod("getDiagnostics", [], $this->context);
        $this->assertStringContainsString("0.0.2", $diag["update_status"]);
        $this->assertStringContainsString("0.0.3", $diag["update_status"]);
        $this->assertStringContainsString("update is available", $diag["update_status"]);
    }

    public function testGetDiagnosticsAnnouncesUpToDate(): void
    {
        $this->installCliHelper();
        $this->cannedOutput("omv-agent-station check-update", [
            '{"current_version":"0.0.3","latest_version":"0.0.3","update_available":false}',
        ]);

        $service = $this->newService();
        $service->callMethod("setSettings", ["data_dir" => $this->dataDir], $this->context);

        $diag = $service->callMethod("getDiagnostics", [], $this->context);
        $this->assertStringContainsString("latest version", $diag["update_status"]);
    }

    // -------------------------------------------------------------------
    // restartServices
    // -------------------------------------------------------------------

    public function testRestartServicesDoesNothingWithoutCliHelper(): void
    {
        $service = $this->newService();
        $service->callMethod("restartServices", [], $this->context);
        $this->assertSame([], Process::$log);
    }

    public function testRestartServicesInvokesCliRestart(): void
    {
        $this->installCliHelper();
        $service = $this->newService();
        $service->callMethod("restartServices", [], $this->context);
        $this->assertSame(["omv-agent-station restart"], $this->executedCommands());
    }

    // -------------------------------------------------------------------
    // getLogs
    // -------------------------------------------------------------------

    public function testGetLogsReturnsEmptyStringWithoutCliHelper(): void
    {
        $service = $this->newService();
        $this->assertSame(["logs" => ""], $service->callMethod("getLogs", [], $this->context));
        $this->assertSame([], Process::$log);
    }

    public function testGetLogsDefaultsToLitellmService(): void
    {
        $this->installCliHelper();
        $this->cannedOutput("omv-agent-station logs litellm", ["line one", "line two"]);

        $service = $this->newService();
        $result = $service->callMethod("getLogs", [], $this->context);

        $this->assertSame("line one\nline two", $result["logs"]);
        $this->assertContains("omv-agent-station logs litellm", $this->executedCommands());
    }

    public function testGetLogsHonorsRequestedService(): void
    {
        $this->installCliHelper();
        $this->cannedOutput("omv-agent-station logs syncthing", ["sync log"]);

        $service = $this->newService();
        $result = $service->callMethod("getLogs", ["service" => "syncthing"], $this->context);

        $this->assertSame("sync log", $result["logs"]);
        $this->assertContains("omv-agent-station logs syncthing", $this->executedCommands());
    }

    public function testGetLogsWithEmptyOutputReturnsEmptyString(): void
    {
        $this->installCliHelper();
        $service = $this->newService();
        $this->assertSame("", $service->callMethod("getLogs", ["service" => "telegram-bot"], $this->context)["logs"]);
    }

    // -------------------------------------------------------------------
    // checkForUpdate
    // -------------------------------------------------------------------

    public function testCheckForUpdateReportsMissingCliHelper(): void
    {
        $service = $this->newService();
        $result = $service->callMethod("checkForUpdate", [], $this->context);
        $this->assertSame("omv-agent-station CLI helper not found.", $result["error"]);
    }

    public function testCheckForUpdateReturnsParsedVersionInfo(): void
    {
        $this->installCliHelper();
        $this->cannedOutput("omv-agent-station check-update", [
            '{"current_version":"0.0.2","latest_version":"0.0.9","update_available":true}',
        ]);

        $service = $this->newService();
        $result = $service->callMethod("checkForUpdate", [], $this->context);

        $this->assertSame("0.0.2", $result["current_version"]);
        $this->assertSame("0.0.9", $result["latest_version"]);
        $this->assertTrue($result["update_available"]);
        $this->assertArrayNotHasKey("error", $result);
    }

    public function testCheckForUpdateReportsMalformedJson(): void
    {
        $this->installCliHelper();
        $this->cannedOutput("omv-agent-station check-update", ["curl: (6) Could not resolve host"]);

        $service = $this->newService();
        $result = $service->callMethod("checkForUpdate", [], $this->context);
        $this->assertSame("Could not parse update check response.", $result["error"]);
    }

    public function testCheckForUpdateRejectsNonArrayJson(): void
    {
        // Valid JSON, wrong shape -- json_decode succeeds and returns a scalar,
        // which would become a TypeError against the `: array` return type if
        // the is_array() guard were ever dropped.
        $this->installCliHelper();
        $this->cannedOutput("omv-agent-station check-update", ['"just a string"']);

        $service = $this->newService();
        $result = $service->callMethod("checkForUpdate", [], $this->context);
        $this->assertSame("Could not parse update check response.", $result["error"]);
    }

    public function testCheckForUpdateHandlesEmptyCliOutput(): void
    {
        $this->installCliHelper();
        $service = $this->newService();
        $result = $service->callMethod("checkForUpdate", [], $this->context);
        $this->assertSame("Could not parse update check response.", $result["error"]);
    }

    // -------------------------------------------------------------------
    // installClaudeCli / updatePlugin (background processes)
    // -------------------------------------------------------------------

    public function testInstallClaudeCliRunsTheInstallerInBackground(): void
    {
        $service = $this->newService();
        $bgStatusFilename = $service->callMethod("installClaudeCli", [], $this->context);

        $this->assertIsString($bgStatusFilename);
        $this->assertNotSame("", $bgStatusFilename);
        $this->assertSame(["omv-agent-station install-claude-cli"], $this->executedCommands());

        @unlink($bgStatusFilename);
    }

    public function testUpdatePluginRunsTheUpdaterInBackground(): void
    {
        $service = $this->newService();
        $bgStatusFilename = $service->callMethod("updatePlugin", [], $this->context);

        $this->assertIsString($bgStatusFilename);
        $this->assertSame(["omv-agent-station update-plugin"], $this->executedCommands());

        @unlink($bgStatusFilename);
    }

    public function testBackgroundMethodsRunEvenWithoutTheCliHelperOnDisk(): void
    {
        // Neither method guards on file_exists -- install-claude-cli is
        // specifically the thing you run when the tooling ISN'T there yet.
        $this->assertFileDoesNotExist($this->cliPath);
        $service = $this->newService();
        $service->callMethod("installClaudeCli", [], $this->context);
        $this->assertNotEmpty(Process::$log);
    }
}
