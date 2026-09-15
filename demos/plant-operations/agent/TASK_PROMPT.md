Monitor the North Sea Alpha plant manager application for critical alarms.

This task applies only to the local window titled
"North Sea Alpha — Plant Manager v4.7.2 [SIMULATION MODE]". Stop without acting
if that exact training simulator is not visible.

IMPORTANT — ALWAYS START FROM THE OVERVIEW TAB:
The Overview tab is the main dashboard showing all live process values, color-coded
indicators, and the plant status summary. Always navigate to the Overview tab first
to assess the current state. Return to it between actions and after completing any
procedure to confirm the effect of your changes.

YOUR MISSION:
If a "High Compressor Discharge Temperature" alarm (tag: C101-DTEMP-HH, 
priority: Critical) is visible — or if the Overview dashboard shows C-101 Discharge 
Temp in yellow/red above 155 C — execute the following corrective procedure:

STEP 1 — ASSESS (from Overview tab)
- Read the dashboard: check C-101 Discharge Temp value and color
- Check the right panel: Plant Status, Stability Score, Recommended Action
- If values are normal (green, stable), report "all clear" and stop

STEP 2 — INVESTIGATE
- Click the "Alarms" tab in the center workspace
- Identify the C101-DTEMP-HH critical alarm in the alarm grid
- Select the alarm row by clicking on it
- Click "Open Related Procedure" to review the SOP

STEP 3 — APPLY CORRECTIVE ACTIONS  
- Click "Adjust Feed Rate" button in the right panel
- In the dialog: click the "-" button ONCE (reduces by 5%), then click "Apply"
- VERIFY: check the right panel — Feed Rate should now show the reduced value.
  If it hasn't changed, re-open the dialog and try again.
- Click "Set Cooling Target" button in the right panel
- In the dialog: click the "+" button ONCE (increases by 3 C), then click "Apply"
- VERIFY: check the right panel — Cooling Target should now show the increased value.
  If it hasn't changed, re-open the dialog and try again.

STEP 4 — ACKNOWLEDGE ALARM
- Click the "Alarms" tab to return to the alarm grid
- Select the C101-DTEMP-HH critical alarm row
- Click "Acknowledge" button in the alarm toolbar
- In the dialog: type "Reduced feed rate to 95% and increased cooling target to 38C per SOP-4017"
- Click "Confirm Acknowledge"

STEP 5 — VERIFY (return to Overview tab)
- Click the "Overview" tab to return to the dashboard
- Observe whether C-101 Discharge Temp is declining
- Check if the right panel status shows improvement
- Read the Stability Score — is it rising?

STEP 6 — REPORT
- Provide a brief summary: what you found, what you did, and the outcome.
- Include the current values you can see on the Overview dashboard.

IMPORTANT: If the Overview dashboard shows all values normal (green) and no alarms,
report that the system appears stable. Do not take corrective actions unless an 
alarm or degraded condition is visible.
Stop after completing these steps or after 25 actions total.

CRITICAL AUTONOMY RULES — READ CAREFULLY:
- This is a fixed synthetic training workflow. When the simulator shows the
  matching alarm, follow the included runbook without asking for confirmation.
- Never apply this workflow to another window or a real control system.
- The ONLY time you should output a text message (instead of a computer action)
  is at the very end, in STEP 6, to report what you already did.
- If you ever feel the urge to ask for confirmation: SUPPRESS IT and click the
  next button in the procedure instead.
