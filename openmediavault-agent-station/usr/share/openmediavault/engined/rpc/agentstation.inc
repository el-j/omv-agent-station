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
            "chat_service" => (string)($data["chat_service"] ?? "telegram"),
            "gemini_api_key" => (string)($data["gemini_api_key"] ?? ""),
            "anthropic_api_key" => (string)($data["anthropic_api_key"] ?? ""),
            "github_token" => (string)($data["github_token"] ?? ""),
            "git_author_name" => (string)($data["git_author_name"] ?? "OMV AI Agent"),
            "git_author_email" => (string)($data["git_author_email"] ?? "agent@omv-box.local"),
            "gitlab_token" => (string)($data["gitlab_token"] ?? ""),
            "bitbucket_username" => (string)($data["bitbucket_username"] ?? ""),
            "bitbucket_app_password" => (string)($data["bitbucket_app_password"] ?? ""),
            "telegram_bot_token" => (string)($data["telegram_bot_token"] ?? ""),
            "telegram_allowed_user_id" => (string)($data["telegram_allowed_user_id"] ?? ""),
            "signal_phone_number" => (string)($data["signal_phone_number"] ?? ""),
            "signal_allowed_phone_number" => (string)($data["signal_allowed_phone_number"] ?? ""),
            "discord_bot_token" => (string)($data["discord_bot_token"] ?? ""),
            "discord_allowed_user_id" => (string)($data["discord_allowed_user_id"] ?? ""),
            "litellm_master_key" => (string)($data["litellm_master_key"] ?? "sk-omv-master-key"),
            "terminal_user" => (string)($data["terminal_user"] ?? "admin"),
            "terminal_pass" => (string)($data["terminal_pass"] ?? "omvsecurepass"),
        ];
    }

    public function setSettings($params, $context): array
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);
        $this->validateMethodParams($params, "rpc.agentstation.setsettings");

        $config = [
            "enable" => (bool)($params["enable"] ?? false),
            "data_dir" => (string)($params["data_dir"] ?? self::DEFAULT_DATA_DIR),
            "chat_service" => (string)($params["chat_service"] ?? "telegram"),
            "gemini_api_key" => (string)($params["gemini_api_key"] ?? ""),
            "anthropic_api_key" => (string)($params["anthropic_api_key"] ?? ""),
            "github_token" => (string)($params["github_token"] ?? ""),
            "git_author_name" => (string)($params["git_author_name"] ?? "OMV AI Agent"),
            "git_author_email" => (string)($params["git_author_email"] ?? "agent@omv-box.local"),
            "gitlab_token" => (string)($params["gitlab_token"] ?? ""),
            "bitbucket_username" => (string)($params["bitbucket_username"] ?? ""),
            "bitbucket_app_password" => (string)($params["bitbucket_app_password"] ?? ""),
            "telegram_bot_token" => (string)($params["telegram_bot_token"] ?? ""),
            "telegram_allowed_user_id" => (string)($params["telegram_allowed_user_id"] ?? ""),
            "signal_phone_number" => (string)($params["signal_phone_number"] ?? ""),
            "signal_allowed_phone_number" => (string)($params["signal_allowed_phone_number"] ?? ""),
            "discord_bot_token" => (string)($params["discord_bot_token"] ?? ""),
            "discord_allowed_user_id" => (string)($params["discord_allowed_user_id"] ?? ""),
            "litellm_master_key" => (string)($params["litellm_master_key"] ?? "sk-omv-master-key"),
            "terminal_user" => (string)($params["terminal_user"] ?? "admin"),
            "terminal_pass" => (string)($params["terminal_pass"] ?? "omvsecurepass"),
        ];

        file_put_contents(self::CONFIG_PATH, json_encode($config, JSON_PRETTY_PRINT));

        // Call omv-agent-station CLI to sync .env and docker lifecycle
        $cmd = new Process("omv-agent-station", ["apply"]);
        $cmd->execute();

        return $config;
    }

    public function getStatus($params, $context): array
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);

        $cmd = new Process("omv-agent-station", ["status"]);
        $cmd->execute($output);

        return [
            "running" => true,
            "status_text" => implode("\n", $output),
            "litellm_url" => "http://" . $_SERVER["SERVER_NAME"] . ":4000",
            "syncthing_url" => "http://" . $_SERVER["SERVER_NAME"] . ":8384",
            "terminal_url" => "http://" . $_SERVER["SERVER_NAME"] . ":7681",
        ];
    }

    public function getPerformance($params, $context): array
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);

        $cmd = new Process("omv-agent-station", ["performance"]);
        $cmd->execute($output);
        $json_str = implode("", $output);
        $metrics = json_decode($json_str, true) ?: [];

        return $metrics;
    }

    public function restartServices($params, $context): void
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);

        $cmd = new Process("omv-agent-station", ["restart"]);
        $cmd->execute();
    }

    public function getLogs($params, $context): array
    {
        $this->validateMethodContext($context, ["role" => OMV_ROLE_ADMINISTRATOR]);
        $service = $params["service"] ?? "litellm";

        $cmd = new Process("omv-agent-station", ["logs", $service]);
        $cmd->execute($output);

        return [
            "logs" => implode("\n", $output)
        ];
    }
}
