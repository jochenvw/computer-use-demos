import os

# Azure AI Foundry
AZURE_AI_FOUNDRY_ENDPOINT = os.environ.get("AZURE_AI_FOUNDRY_ENDPOINT", "")
MODEL_DEPLOYMENT = os.environ.get("MODEL_DEPLOYMENT", "computer-use-preview")
AZURE_API_KEY = os.environ.get("AZURE_API_KEY", "")
ALLOW_COMPUTER_CONTROL = os.environ.get("ALLOW_COMPUTER_CONTROL", "") == "1"
TARGET_WINDOW_TITLE = "North Sea Alpha — Plant Manager v4.7.2 [SIMULATION MODE]"


def validate(*, live: bool = False):
    """Raise early if required config is missing."""
    if not AZURE_AI_FOUNDRY_ENDPOINT:
        raise EnvironmentError(
            "Set AZURE_AI_FOUNDRY_ENDPOINT environment variable "
            "(e.g. https://your-resource.services.ai.azure.com)"
        )
    if live and not ALLOW_COMPUTER_CONTROL:
        raise EnvironmentError(
            "Live control is disabled. Set ALLOW_COMPUTER_CONTROL=1 only after "
            "starting the local Plant Manager simulator."
        )

# Display
DISPLAY_WIDTH = 1400
DISPLAY_HEIGHT = 900
ENVIRONMENT = "windows"

# Safety limits
MAX_STEPS = 25
MAX_PARAMETER_CHANGES = 2
REPEAT_ACTION_LIMIT = 3

# Timing (seconds)
ACTION_DELAY = 0.75
SCREENSHOT_DELAY = 0.3
POLL_INTERVAL = 10          # seconds between monitoring checks when idle


def print_config():
    auth_mode = "API Key" if AZURE_API_KEY else "Entra ID (DefaultAzureCredential)"
    print("=== SRE Agent Configuration ===")
    print(f"  Endpoint:             {AZURE_AI_FOUNDRY_ENDPOINT}")
    print(f"  Model:                {MODEL_DEPLOYMENT}")
    print(f"  Auth:                 {auth_mode}")
    print(f"  Display:              {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}")
    print(f"  Environment:          {ENVIRONMENT}")
    print(f"  Max steps:            {MAX_STEPS}")
    print(f"  Max param changes:    {MAX_PARAMETER_CHANGES}")
    print(f"  Repeat action limit:  {REPEAT_ACTION_LIMIT}")
    print(f"  Action delay:         {ACTION_DELAY}s")
    print(f"  Screenshot delay:     {SCREENSHOT_DELAY}s")
