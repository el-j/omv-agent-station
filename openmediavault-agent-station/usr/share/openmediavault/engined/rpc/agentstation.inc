<?php
/**
 * OpenMediaVault Agent Station RPC Service
 *
 * @author    Fabian <dev@local>
 * @copyright 2026 Fabian
 * @license   GPL-3.0-or-later
 */

namespace OMV\Engined\Rpc;

use OMV\Rpc\ServiceAbstract;
use OMV\Rpc\Exception as RpcException;
use OMV\System\Process;

class AgentStation extends ServiceAbstract
{
    private const CONFIG_PATH = "/etc/openmediavault-agent-station.json";
    private const DEFAULT_DATA_DIR = "/srv/dev-data";
    private const STACK_DIR = "/usr/share/openmediavault/agent-station";

    public function getName(): string
    {
        return "AgentStation";
    }

    public function initialize(): void
    {
        $this->registerMethod("getSettings");
        $this->registerMethod("setSettings");
        $this->registerMethod("getStatus");
        $this->registerMethod("getDiagnostics");
        $this->registerMethod("getPerformance");
        $this->registerMethod("restartServices");
        $this->registerMethod("getLogs");
    }

    public function getSettings($params, $context): array
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);

        if (file_exists(self::CONFIG_PATH)) {
            $data = json_decode(file_get_contents(self::CONFIG_PATH), true) ?: [];
        } elseif (file_exists("/etc/openmediavault-ai-orchestrator.json")) {
            $data = json_decode(file_get_contents("/etc/openmediavault-ai-orchestrator.json"), true) ?: [];
        } else {
            $data = [];
        }

        return [
            "enable" => (bool)($data["enable"] ?? false),
            "data_dir" => (string)($data["data_dir"] ?? self::DEFAULT_DATA_DIR),
            "enable_aimodels" => (bool)($data["enable_aimodels"] ?? true),
            "enable_gemini" => (bool)($data["enable_gemini"] ?? true),
            "gemini_api_key" => (string)($data["gemini_api_key"] ?? ""),
            "enable_anthropic" => (bool)($data["enable_anthropic"] ?? true),
            "anthropic_api_key" => (string)($data["anthropic_api_key"] ?? ""),
            "enable_github_models" => (bool)($data["enable_github_models"] ?? true),
            "github_token" => (string)($data["github_token"] ?? ""),
            "enable_git" => (bool)($data["enable_git"] ?? true),
            "git_author_name" => (string)($data["git_author_name"] ?? "OMV AI Agent"),
            "git_author_email" => (string)($data["git_author_email"] ?? "agent@omv-box.local"),
            "enable_github" => (bool)($data["enable_github"] ?? true),
            "github_git_user" => (string)($data["github_git_user"] ?? ""),
            "github_git_token" => (string)($data["github_git_token"] ?? ""),
            "enable_gitlab" => (bool)($data["enable_gitlab"] ?? false),
            "gitlab_token" => (string)($data["gitlab_token"] ?? ""),
            "enable_bitbucket" => (bool)($data["enable_bitbucket"] ?? false),
            "bitbucket_username" => (string)($data["bitbucket_username"] ?? ""),
            "bitbucket_app_password" => (string)($data["bitbucket_app_password"] ?? ""),
            "enable_chat" => (bool)($data["enable_chat"] ?? true),
            "chat_service" => (string)($data["chat_service"] ?? "telegram"),
            "enable_telegram" => (bool)($data["enable_telegram"] ?? true),
            "telegram_bot_token" => (string)($data["telegram_bot_token"] ?? ""),
            "telegram_allowed_user_id" => (string)($data["telegram_allowed_user_id"] ?? ""),
            "enable_signal" => (bool)($data["enable_signal"] ?? false),
            "signal_phone_number" => (string)($data["signal_phone_number"] ?? ""),
            "signal_allowed_phone_number" => (string)($data["signal_allowed_phone_number"] ?? ""),
            "enable_discord" => (bool)($data["enable_discord"] ?? false),
            "discord_bot_token" => (string)($data["discord_bot_token"] ?? ""),
            "discord_allowed_user_id" => (string)($data["discord_allowed_user_id"] ?? ""),
            "enable_security" => (bool)($data["enable_security"] ?? true),
            "litellm_master_key" => (string)($data["litellm_master_key"] ?? "sk-omv-secret-master-key"),
            "terminal_user" => (string)($data["terminal_user"] ?? "admin"),
            "terminal_pass" => (string)($data["terminal_pass"] ?? "omvsecurepass"),
        ];
    }

    public function setSettings($params, $context): array
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);
        $this->validateMethodParams($params, "rpc.agentstation.setsettings");

        // Merge with existing configuration so partial submenu updates preserve other tabs
        $existing = [];
        if (file_exists(self::CONFIG_PATH)) {
            $existing = json_decode(file_get_contents(self::CONFIG_PATH), true) ?: [];
        }

        $sanitized = [];
        foreach ($params as $k => $v) {
            $sanitized[$k] = ($v === null) ? "" : $v;
        }

        $config = array_merge($existing, $sanitized);

        file_put_contents(self::CONFIG_PATH, json_encode($config, JSON_PRETTY_PRINT));

        // Call omv-agent-station apply-bg asynchronously so response returns immediately (<50ms)
        if (file_exists("/usr/sbin/omv-agent-station")) {
            $cmd = new Process("omv-agent-station", ["apply-bg"]);
            $cmd->execute();
        }

        return $config;
    }

    public function getStatus($params, $context): array
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);

        $settings = $this->getSettings([], $context);
        $masterEnabled = (bool)($settings["enable"] ?? false);

        $perf = $this->getPerformance([], $context);
        $containers = $perf["containers"] ?? [];
        $hasRunningContainer = false;
        foreach ($containers as $isRunning) {
            if ($isRunning) {
                $hasRunningContainer = true;
                break;
            }
        }

        $engineDetail = "Stopped";
        if ($masterEnabled) {
            $engineDetail = $hasRunningContainer ? "Active (Containers Running)" : "Provisioning (Pulling Images / Starting)...";
        }

        $gitProviders = [];
        if (!empty($settings["enable_github"])) $gitProviders[] = "GitHub";
        if (!empty($settings["enable_gitlab"])) $gitProviders[] = "GitLab";
        if (!empty($settings["enable_bitbucket"])) $gitProviders[] = "Bitbucket";
        $gitDetail = !empty($gitProviders) ? implode(", ", $gitProviders) : "Local Only";

        return [
            [
                "name" => "Engine",
                "enabled" => $masterEnabled && $hasRunningContainer,
                "detail" => $engineDetail
            ],
            [
                "name" => "AI Models",
                "enabled" => $masterEnabled && (bool)($settings["enable_aimodels"] ?? true),
                "detail" => !empty($settings["gemini_api_key"]) || !empty($settings["anthropic_api_key"]) || !empty($settings["github_token"]) ? "Keys configured" : "No keys set"
            ],
            [
                "name" => "Git Sync",
                "enabled" => $masterEnabled && (bool)($settings["enable_git"] ?? true),
                "detail" => $gitDetail
            ],
            [
                "name" => "Messenger",
                "enabled" => $masterEnabled && (bool)($settings["enable_chat"] ?? true) && ($settings["chat_service"] ?? "none") !== "none",
                "detail" => ucfirst((string)($settings["chat_service"] ?? "telegram"))
            ],
            [
                "name" => "Security",
                "enabled" => $masterEnabled && (bool)($settings["enable_security"] ?? true),
                "detail" => "Port 7681 protected"
            ]
        ];
    }

    public function getDiagnostics($params, $context): array
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);

        $settings = $this->getSettings([], $context);
        $dataDir = $settings["data_dir"] ?? "/srv/dev-data";

        // 1. Container matrix
        $perf = $this->getPerformance([], $context);
        $details = $perf["container_details"] ?? [];
        $knownContainers = [
            "LiteLLM Gateway" => ["port" => "Port 4000 (AI Gateway)"],
            "Web Terminal" => ["port" => "Port 7681 (Sandboxed Agent)"],
            "Syncthing" => ["port" => "Port 8384 (File Sync)"],
            "Telegram Bot" => ["port" => "Telegram Bot Relay"]
        ];

        foreach ($knownContainers as $cname => $meta) {
            $info = $details[$cname] ?? [];
            $st = $info["status"] ?? "Stopped";
            $containerLines[] = sprintf("%-22s | %-32s | %-20s", $cname, $st, $meta["port"]);
        }
        $containerStatus = implode("\n", $containerLines);

        // 2. Storage & Workspace metrics
        $workspaceDir = $dataDir . "/workspace";
        $obsidianDir = $dataDir . "/obsidian";
        $workspaceSize = "0 MB";
        $obsidianSize = "0 MB";
        $diskFree = "N/A";

        if (is_dir($workspaceDir)) {
            $out = [];
            exec("du -sh " . escapeshellarg($workspaceDir) . " 2>/dev/null | awk '{print $1}'", $out);
            $workspaceSize = $out[0] ?? "0 MB";
        }
        if (is_dir($obsidianDir)) {
            $out = [];
            exec("du -sh " . escapeshellarg($obsidianDir) . " 2>/dev/null | awk '{print $1}'", $out);
            $obsidianSize = $out[0] ?? "0 MB";
        }
        $dfOut = [];
        exec("df -h " . escapeshellarg($dataDir) . " 2>/dev/null | tail -n 1 | awk '{print $4 \" available of \" $2 \" (\" $5 \" used)\"}'", $dfOut);
        $diskFree = $dfOut[0] ?? "N/A";

        $storageLines = [];
        $storageLines[] = sprintf("📁 Workspace Projects Directory : %s (%s)", $workspaceDir, $workspaceSize);
        $storageLines[] = sprintf("📓 Obsidian Knowledge Vault     : %s (%s)", $obsidianDir, $obsidianSize);
        $storageLines[] = sprintf("💾 Storage Volume Available     : %s", $diskFree);
        $storageStatus = implode("\n", $storageLines);

        // 3. AI Providers Connected
        $aiLines = [];
        $aiLines[] = "🤖 Active AI Provider Routing & Gateway Connections:";
        $aiLines[] = sprintf("  • Google Gemini Studio   : %s", (!empty($settings["gemini_api_key"]) ? "✅ Connected (Gemini 2.5 / 3.7 Pro & Flash)" : "⚪ Not Configured"));
        $aiLines[] = sprintf("  • GitHub Models / Copilot: %s", (!empty($settings["github_token"]) ? "✅ Connected (GPT-4o, DeepSeek-R1, o1)" : "⚪ Not Configured"));
        $aiLines[] = sprintf("  • Mistral AI Direct      : %s", (!empty($settings["mistral_api_key"]) ? "✅ Connected (Codestral, Mistral Large)" : "⚪ Not Configured"));
        $aiLines[] = sprintf("  • OpenRouter / Z.AI      : %s", (!empty($settings["openrouter_api_key"]) ? "✅ Connected (Universal Model Aggregator)" : "⚪ Not Configured"));
        $aiLines[] = sprintf("  • DeepSeek Direct API    : %s", (!empty($settings["deepseek_api_key"]) ? "✅ Connected (DeepSeek-V3, DeepSeek-R1)" : "⚪ Not Configured"));
        $aiLines[] = sprintf("  • Claude Code CLI        : %s", (file_exists("/usr/local/bin/claude") ? "✅ Pre-installed in Sandboxed Container" : "⚪ Installable via AI Models tab"));
        $aiStatus = implode("\n", $aiLines);

        // 4. Live execution logs
        $statusText = "";
        if (file_exists("/usr/sbin/omv-agent-station")) {
            $cmd = new Process("omv-agent-station", ["logs", "all"]);
            $cmd->execute($output);
            $cleanLines = [];
            foreach ($output as $line) {
                // Strip ANSI escape sequences
                $clean = preg_replace('/\x1B\[[0-9;]*[a-zA-Z]/', '', $line);
                if (trim($clean) !== "") {
                    $cleanLines[] = $clean;
                }
            }
            // Keep last 150 lines
            $slice = array_slice($cleanLines, -150);
            $statusText = implode("\n", $slice);
        }

        return [
            "container_status" => $containerStatus,
            "storage_status" => $storageStatus,
            "ai_status" => $aiStatus,
            "log_output" => $statusText ?: "No startup logs recorded yet. Enable the Agent Station in Overview to provision containers."
        ];
    }

    public function getPerformance($params, $context): array
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);

        if (file_exists("/usr/sbin/omv-agent-station")) {
            $cmd = new Process("omv-agent-station", ["performance"]);
            $cmd->execute($output);
            $json_str = implode("", $output);
            return json_decode($json_str, true) ?: [];
        }

        return [];
    }

    public function restartServices($params, $context): void
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);

        if (file_exists("/usr/sbin/omv-agent-station")) {
            $cmd = new Process("omv-agent-station", ["restart"]);
            $cmd->execute();
        }
    }

    public function getLogs($params, $context): array
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);
        $service = $params["service"] ?? "litellm";

        if (file_exists("/usr/sbin/omv-agent-station")) {
            $cmd = new Process("omv-agent-station", ["logs", $service]);
            $cmd->execute($output);
            return [
                "logs" => implode("\n", $output)
            ];
        }

        return [
            "logs" => ""
        ];
    }

    public function installClaudeCli($params, $context)
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);

        return $this->execBgProc(function ($bgStatusFilename, $bgOutputFilename) {
            $cmd = new Process("omv-agent-station", ["install-claude-cli"]);
            $cmd->setRedirectOutput(true);
            $cmd->setAsync(false);
            $cmd->execute($output);
            file_put_contents($bgOutputFilename, implode("\n", $output));
        });
    }
}
