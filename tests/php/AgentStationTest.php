<?php
/**
 * PHPUnit coverage for openmediavault-agent-station's AgentStation RPC
 * service (issue #21: agentstation.inc had zero tests -- this is how the
 * installClaudeCli unregistered-method bug fixed in PR #11 went
 * unnoticed).
 */

use OMV\Engined\Rpc\AgentStation;
use PHPUnit\Framework\TestCase;

final class AgentStationTest extends TestCase
{
    private string $configPath;
    private string $dataDir;
    private array $context;

    protected function setUp(): void
    {
        $this->configPath = sys_get_temp_dir() . "/agentstation_test_config_" . uniqid() . ".json";
        putenv("AGENTSTATION_TEST_CONFIG_PATH=" . $this->configPath);

        $this->dataDir = sys_get_temp_dir() . "/agentstation_test_data_" . uniqid();
        mkdir($this->dataDir, 0755, true);

        $this->context = ["username" => "admin", "role" => OMV_ROLE_ADMINISTRATOR];
    }

    protected function tearDown(): void
    {
        putenv("AGENTSTATION_TEST_CONFIG_PATH");
        @unlink($this->configPath);
        $this->rrmdir($this->dataDir);
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
}
