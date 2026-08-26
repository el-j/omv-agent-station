<?php
/**
 * Minimal stand-ins for the OpenMediaVault core PHP classes
 * usr/share/openmediavault/engined/rpc/agentstation.inc depends on
 * (\OMV\Rpc\ServiceAbstract, \OMV\Rpc\Exception, \OMV\System\Process).
 *
 * The real openmediavault package isn't installable outside an actual OMV
 * box (it's not on Packagist and pulls in a deep framework -- config
 * database, RPC dispatch, background-process forking), so this vendors
 * only the exact interface AgentStation actually calls, modeled directly
 * against the real class at
 * /usr/share/php/openmediavault/rpc/serviceabstract.inc on a live OMV
 * install. Mirrors the same "stub the framework boundary" approach
 * tests/stubs.py already uses for discord.py/telegram.ext in the Python
 * suite.
 */

namespace {
    if (!defined("OMV_ROLE_ADMINISTRATOR")) {
        define("OMV_ROLE_ADMINISTRATOR", 0x1);
    }
}

namespace OMV\Rpc {

    class Exception extends \Exception
    {
        public function __construct($message, ...$args)
        {
            if (!empty($args)) {
                $message = vsprintf($message, $args);
            }
            parent::__construct($message);
        }
    }

    abstract class ServiceAbstract
    {
        private $registeredMethods = [];

        abstract public function getName();
        abstract public function initialize();

        final protected function registerMethod($rpcName, $methodName = null)
        {
            $methodName = is_null($methodName) ? $rpcName : $methodName;
            if (!method_exists($this, $methodName)) {
                throw new Exception(
                    "The method '%s' does not exist for RPC service '%s'.",
                    $methodName,
                    $this->getName()
                );
            }
            $this->registeredMethods[$rpcName] = $methodName;
            return true;
        }

        final public function hasMethod($name)
        {
            return array_key_exists($name, $this->registeredMethods);
        }

        /**
         * Not part of the real ServiceAbstract's public API (real RPC
         * dispatch goes through \OMV\Rpc\Rpc::call()), but the simplest way
         * for the test harness to invoke a registered method by its public
         * RPC name rather than reaching into the internal method-name map.
         */
        final public function callMethod($name, $params, $context)
        {
            if (!$this->hasMethod($name)) {
                throw new Exception(
                    "The method '%s' does not exist for RPC service '%s'.",
                    $name,
                    $this->getName()
                );
            }
            return call_user_func([$this, $this->registeredMethods[$name]], $params, $context);
        }

        final public function getRegisteredMethodNames()
        {
            return array_keys($this->registeredMethods);
        }

        final protected function validateMethodContext($context, $required)
        {
            if (array_key_exists("username", $required)) {
                $requiredUsernames = is_array($required["username"]) ? $required["username"] : [$required["username"]];
                if (!in_array($context["username"] ?? null, $requiredUsernames, true)) {
                    throw new Exception("Invalid context username.");
                }
            }
            if (array_key_exists("role", $required)) {
                if (!(($context["role"] ?? 0) & $required["role"])) {
                    throw new Exception("Invalid context role.");
                }
            }
        }

        /**
         * Real OMV validates $params against a JSON schema registered for
         * this RPC method via ParamsValidator, which isn't vendored here.
         * This intentionally accepts anything -- these tests exercise
         * setSettings/getStatus's own logic, not OMV's schema validator.
         */
        final protected function validateMethodParams($params, $schema)
        {
        }

        /**
         * Real OMV forks a child process and runs $childFn there, returning
         * a status filename the caller polls. Forking is unnecessary
         * complexity for a test harness -- this runs $childFn synchronously
         * so its side effects are immediately observable, and returns a
         * plausible fake status filename.
         */
        public function execBgProc(\Closure $childFn, ?\Closure $errorFn = null, ?\Closure $finallyFn = null)
        {
            $bgStatusFilename = tempnam(sys_get_temp_dir(), "agentstation_test_bgstatus_");
            $bgOutputFilename = tempnam(sys_get_temp_dir(), "agentstation_test_bgoutput_");
            try {
                $childFn($bgStatusFilename, $bgOutputFilename);
            } finally {
                if ($finallyFn !== null) {
                    $finallyFn();
                }
            }
            return $bgStatusFilename;
        }
    }
}

namespace OMV\System {

    class Process
    {
        /** @var array<int, array<int, string>> Every command this stub was asked to run, for assertions. */
        public static $log = [];

        private $command;
        private $args;

        public function __construct($command, array $args = [])
        {
            $this->command = $command;
            $this->args = $args;
        }

        public function setRedirectOutput($flag)
        {
        }

        public function setAsync($flag)
        {
        }

        public function execute(&$output = null)
        {
            self::$log[] = array_merge([$this->command], $this->args);
            $output = [];
            return 0;
        }
    }
}
