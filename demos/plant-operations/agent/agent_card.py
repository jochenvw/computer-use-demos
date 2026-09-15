"""A2A agent card for the SRE Operational Reliability Agent.

Defines the agent's "digital business card" used by other agents and
Azure AI Foundry to discover capabilities and invoke this agent via
the Agent-to-Agent (A2A) protocol.
"""

from a2a.types import AgentCard, AgentCapabilities, AgentSkill


def build_agent_card(host: str = "localhost", port: int = 10100) -> AgentCard:
    """Build and return the A2A agent card for the SRE agent."""

    skills = [
        AgentSkill(
            id="detect_plant_alarm",
            name="Detect Plant Alarm",
            description=(
                "Monitors the North Sea Alpha plant manager application for "
                "critical alarms by analyzing the UI via screenshots. Detects "
                "alarm conditions such as high compressor discharge temperature, "
                "rising separator pressure, or cooling loop underperformance."
            ),
            tags=["industrial", "sre", "alarm-detection", "monitoring", "plant-operations"],
            examples=[
                "Check the plant manager for any active alarms",
                "Is there a critical alarm on compressor C-101?",
                "Monitor the plant for abnormal conditions",
            ],
        ),
        AgentSkill(
            id="execute_corrective_action",
            name="Execute Corrective Action",
            description=(
                "Executes corrective actions on the plant manager UI following "
                "standard operating procedures (SOPs). Can adjust feed rate, "
                "modify cooling targets, toggle recycle valves, and acknowledge "
                "alarms. Actions are bounded by safety limits (max 15 steps, "
                "max 2 parameter changes)."
            ),
            tags=["industrial", "sre", "corrective-action", "automation", "plant-operations"],
            examples=[
                "Reduce feed rate to 95% to address high discharge temperature",
                "Execute SOP-4017 for high compressor temperature",
                "Acknowledge the critical alarm and apply corrective actions",
            ],
        ),
        AgentSkill(
            id="verify_plant_stability",
            name="Verify Plant Stability",
            description=(
                "Verifies that the plant has stabilized after corrective actions "
                "by checking process values, alarm states, and stability scores "
                "on the plant manager UI."
            ),
            tags=["industrial", "sre", "verification", "monitoring", "plant-operations"],
            examples=[
                "Verify that compressor temperature is declining",
                "Check if the plant is stable after feed rate reduction",
                "Confirm alarms have cleared",
            ],
        ),
    ]

    capabilities = AgentCapabilities(
        streaming=False,
        push_notifications=False,
        state_transition_history=True,
    )

    return AgentCard(
        name="SRE Operational Reliability Agent",
        description=(
            "An autonomous SRE agent that monitors the North Sea Alpha plant "
            "manager desktop application, detects critical alarms, consults "
            "structured runbook procedures (SOPs), and executes corrective "
            "actions through UI automation. Powered by Azure AI Foundry's "
            "computer-use-preview model."
        ),
        version="0.1.0",
        url=f"http://{host}:{port}/",
        skills=skills,
        capabilities=capabilities,
        default_input_modes=["text", "text/plain"],
        default_output_modes=["text", "text/plain"],
    )
