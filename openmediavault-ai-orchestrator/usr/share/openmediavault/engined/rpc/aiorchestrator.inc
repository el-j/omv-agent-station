<?php
/**
 * OpenMediaVault AI Orchestrator RPC Service
 *
 * @author    Fabian <dev@local>
 * @copyright 2026 Fabian
 * @license   GPL-3.0-or-later
 */

namespace OMV\Engined\Rpc;

use OMV\Rpc\ServiceAbstract;
use OMV\Rpc\Exception as RpcException;
use OMV\System\Process;

class AIOrchestrator extends ServiceAbstract
{
    private const CONFIG_PATH = "/etc/openmediavault-ai-orchestrator.json";
    private const DEFAULT_DATA_DIR = "/srv/dev-data";
    private const STACK_DIR = "/usr/share/openmediavault/ai-orchestrator";

    public function getName(): string
    {
        return "AIOrchestrator";
    }

    public function initialize(): void
    {
        $this->registerMethod("getSettings");
        $this->registerMethod("setSettings");
        $this->registerMethod("getStatus");
        $this->registerMethod("restartServices");
        $this->registerMethod("getLogs");
    }

    public function getSettings($params, $context): array
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);

        if (file_exists(self::CONFIG_PATH)) {
            $data = json_decode(file_get_contents(self::CONFIG_PATH), true) ?: [];
        } else {
            $data = [];
        }

        return [
            "enable" => (bool)($data["enable"] ?? false),
            "data_dir" => (string)($data["data_dir"] ?? self::DEFAULT_DATA_DIR),
            "gemini_api_key" => (string)($data["gemini_api_key"] ?? ""),
            "anthropic_api_key" => (string)($data["anthropic_api_key"] ?? ""),
            "github_token" => (string)($data["github_token"] ?? ""),
            "telegram_bot_token" => (string)($data["telegram_bot_token"] ?? ""),
            "telegram_allowed_user_id" => (string)($data["telegram_allowed_user_id"] ?? ""),
            "litellm_master_key" => (string)($data["litellm_master_key"] ?? "sk-omv-master-key"),
            "terminal_user" => (string)($data["terminal_user"] ?? "admin"),
            "terminal_pass" => (string)($data["terminal_pass"] ?? "proliantgen8"),
        ];
    }

    public function setSettings($params, $context): array
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);
        $this->validateMethodParams($params, "rpc.aiorchestrator.setsettings");

        $config = [
            "enable" => (bool)($params["enable"] ?? false),
            "data_dir" => (string)($params["data_dir"] ?? self::DEFAULT_DATA_DIR),
            "gemini_api_key" => (string)($params["gemini_api_key"] ?? ""),
            "anthropic_api_key" => (string)($params["anthropic_api_key"] ?? ""),
            "github_token" => (string)($params["github_token"] ?? ""),
            "telegram_bot_token" => (string)($params["telegram_bot_token"] ?? ""),
            "telegram_allowed_user_id" => (string)($params["telegram_allowed_user_id"] ?? ""),
            "litellm_master_key" => (string)($params["litellm_master_key"] ?? "sk-omv-master-key"),
            "terminal_user" => (string)($params["terminal_user"] ?? "admin"),
            "terminal_pass" => (string)($params["terminal_pass"] ?? "proliantgen8"),
        ];

        file_put_contents(self::CONFIG_PATH, json_encode($config, JSON_PRETTY_PRINT));

        // Call omv-ai-orchestrator CLI to sync .env and docker lifecycle
        $cmd = new Process("omv-ai-orchestrator", ["apply"]);
        $cmd->execute();

        return $config;
    }

    public function getStatus($params, $context): array
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);

        $cmd = new Process("omv-ai-orchestrator", ["status"]);
        $cmd->execute($output);

        return [
            "running" => true,
            "status_text" => implode("\n", $output),
            "litellm_url" => "http://" . $_SERVER["SERVER_NAME"] . ":4000",
            "syncthing_url" => "http://" . $_SERVER["SERVER_NAME"] . ":8384",
            "terminal_url" => "http://" . $_SERVER["SERVER_NAME"] . ":7681",
        ];
    }

    public function restartServices($params, $context): void
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);

        $cmd = new Process("omv-ai-orchestrator", ["restart"]);
        $cmd->execute();
    }

    public function getLogs($params, $context): array
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);
        $service = $params["service"] ?? "litellm";

        $cmd = new Process("omv-ai-orchestrator", ["logs", $service]);
        $cmd->execute($output);

        return [
            "logs" => implode("\n", $output)
        ];
    }
}
