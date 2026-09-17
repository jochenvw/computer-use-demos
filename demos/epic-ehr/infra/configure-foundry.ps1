[CmdletBinding()]
param(
    [Parameter(Mandatory)][uri]$Endpoint,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]*$')][string]$Deployment,
    [string]$ServiceRoot = 'C:\EpicDemo\service'
)

$ErrorActionPreference = 'Stop'
if (-not $Endpoint.IsAbsoluteUri -or $Endpoint.Scheme -ne 'https' -or
    $Endpoint.UserInfo -or $Endpoint.Query -or $Endpoint.Fragment -or
    $Endpoint.AbsolutePath -ne '/') {
    throw 'Endpoint must be the HTTPS Azure OpenAI resource root, without a path or credentials.'
}
$envFile = Join-Path $ServiceRoot '.env'
$python = Join-Path $ServiceRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $envFile) -or -not (Test-Path -LiteralPath $python)) {
    throw 'Install the agent before configuring Foundry.'
}
$lines = @(Get-Content -LiteralPath $envFile)
$updates = [ordered]@{
    AZURE_AI_FOUNDRY_ENDPOINT = $Endpoint.AbsoluteUri.TrimEnd('/')
    MODEL_DEPLOYMENT = $Deployment
}
foreach ($key in $updates.Keys) {
    if (@($lines | Where-Object { $_ -match "^\s*$key\s*=" }).Count -gt 1) {
        throw "Remove duplicate $key entries before continuing."
    }
}
$sdkVersion = & $python -c "from importlib.metadata import version; print(version('github-copilot-sdk'))"
if ($LASTEXITCODE -ne 0) { throw 'Could not read the installed Copilot SDK version.' }
$runtimeRoot = "C:\DemoTools\copilot-runtime\sdk-$sdkVersion"
if (-not (Test-Path -LiteralPath $runtimeRoot)) {
    throw 'Provision the SDK-matched runtime with install-agent.ps1 first.'
}
$previousRuntime = $env:COPILOT_CLI_EXTRACT_DIR
try {
    $env:COPILOT_CLI_EXTRACT_DIR = $runtimeRoot
    @'
import asyncio
import json
import secrets
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from azure.identity import ManagedIdentityCredential
from copilot import CopilotClient, Tool, ToolResult, ToolSet
from copilot.generated.rpc import PermissionDecisionDeniedByRules


async def main():
    marker = secrets.token_hex(16)
    calls = 0

    async def probe(invocation):
        nonlocal calls
        if invocation.arguments:
            raise ValueError("The smoke-test tool takes no arguments.")
        calls += 1
        return ToolResult(text_result_for_llm=marker)

    def deny_permission(request, invocation):
        return PermissionDecisionDeniedByRules(rules=[])

    tool = Tool(
        name="synthetic_probe", description="Return the synthetic verification marker.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=probe, skip_permission=True, defer="never",
    )
    allowed = ToolSet()
    allowed.add_custom(tool.name)
    with ManagedIdentityCredential() as credential, TemporaryDirectory(prefix="epic-foundry-check-") as directory:
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        home = Path(directory)
        work = home / "work"
        work.mkdir()
        async with CopilotClient(
            mode="empty", working_directory=str(work), base_directory=str(home / "home"),
            use_logged_in_user=False, builtin_plugin_directories=[],
            enable_remote_sessions=False, log_level="error",
        ) as client:
            session = await client.create_session(
                model=sys.argv[2],
                provider={
                    "type": "openai", "wire_api": "responses",
                    "base_url": sys.argv[1].rstrip("/") + "/openai/v1",
                    "bearer_token": token.token,
                },
                tools=[tool], available_tools=allowed, on_permission_request=deny_permission,
                working_directory=str(work), enable_skills=False,
                enable_config_discovery=False, skip_custom_instructions=True,
                enable_file_hooks=False, enable_host_git_operations=False,
                enable_session_store=False, plugin_directories=[], mcp_servers={},
                enable_mcp_apps=False, memory={"enabled": False},
                infinite_sessions={"enabled": False}, large_output={"enabled": False},
            )
            try:
                response = await session.send_and_wait(
                    "Call synthetic_probe exactly once, then reply with only the returned marker.",
                    timeout=180,
                )
                if calls != 1 or response is None or response.data.content.strip() != marker:
                    raise RuntimeError("Copilot did not complete the required synthetic tool round trip.")
            finally:
                try:
                    await session.abort()
                finally:
                    try:
                        await session.disconnect()
                    finally:
                        await client.delete_session(session.session_id)
    print(json.dumps({"managedIdentity": True, "copilotToolRoundTrip": True, "deployment": sys.argv[2]}))


asyncio.run(main())
'@ | & $python - $updates.AZURE_AI_FOUNDRY_ENDPOINT $Deployment
    if ($LASTEXITCODE -ne 0) {
        throw 'Foundry/Copilot verification failed; .env was not changed. Check identity RBAC and model availability.'
    }
} finally {
    $env:COPILOT_CLI_EXTRACT_DIR = $previousRuntime
}

# Do not overwrite a configuration that the operator edited during the model check.
if (($lines -join "`n") -cne ((Get-Content -LiteralPath $envFile) -join "`n")) {
    throw 'The .env changed during verification. Retry after the operator finishes editing it.'
}
foreach ($key in $updates.Keys) {
    $found = $false
    $lines = @(
        foreach ($line in $lines) {
            if ($line -match "^\s*$key\s*=") {
                "$key=$($updates[$key])"
                $found = $true
            } else {
                $line
            }
        }
    )
    if (-not $found) { $lines += "$key=$($updates[$key])" }
}
# Update in place to retain the private file ACL and every unrelated setting.
$lines | Set-Content -LiteralPath $envFile -Encoding UTF8
Write-Output 'Foundry verified and configured. Backend, browser opt-in, API token, and running processes are unchanged.'
