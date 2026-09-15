# Demo Script — Plant Manager Simulator (3 minutes)

This walkthrough demonstrates a scenario where an LLM computer-use agent
detects an alarm, investigates, takes corrective action, and verifies
stabilisation.

---

## Setup (~10 seconds)

1. Launch the application. The Overview tab shows all process values in green.
2. Note the **right panel**: Status = NORMAL, Stability = 96/100, no
   recommended action.
3. Note the **status bar**: simulation time is ticking, operator is J. Hansen.

---

## Act 1: Trigger the Alarm (~30 seconds)

1. Click **▶ Scenario 1: High Temp** in the toolbar.
2. Watch the **C-101 Discharge Temp** on the Overview tab:
   - Value rises from ~142 °C toward 165+ °C.
   - The numeric indicator turns **yellow**, then **red**.
3. After ~30 seconds, alarms appear:
   - **C101-DTEMP-HI** (Warning) at 155 °C
   - **C101-DTEMP-HH** (Critical) at 165 °C
4. The right panel updates:
   - Status → DEGRADED or ABNORMAL
   - Active Alarms → 2+
   - Recommended Action → "Reduce feed rate by 5%, increase cooling target"

---

## Act 2: Investigate (~30 seconds)

1. Click the **Alarms** tab (or click **⚠ Acknowledge Alarm** in toolbar).
2. Select the **C101-DTEMP-HH** critical alarm in the grid.
3. Click **Open Related Procedure** — the app switches to the Procedures tab
   and displays **SOP-4017: High Compressor Discharge Temperature**.
4. Read the procedure: it says to reduce feed rate by 5%, increase cooling
   target by 3 °C, and verify recycle valve in AUTO.

---

## Act 3: Take Corrective Action (~60 seconds)

1. Click **🎛 Adjust Feed Rate** in the right panel (or use toolbar → Manual
   Control → Adjust Feed Rate).
   - Current value: ~100%.
   - Enter **95.0** → click **Apply**.
2. Click **❄ Set Cooling Target**.
   - Current value: 35.0 °C.
   - Enter **38.0** → click **Apply**.
3. Click **🔄 Toggle Recycle Valve** (confirm it's in AUTO — if it says AUTO,
   no action needed; if MANUAL-OPEN, toggle it back).
4. Return to the **Alarms** tab. Select the critical alarm and click
   **Acknowledge**. Type a note: "Reduced feed and increased cooling per SOP"
   → click **Confirm Acknowledge**.

---

## Act 4: Verify Stabilisation (~60 seconds)

1. Click the **Trends** tab. Watch the C-101 Discharge Temperature chart:
   - The line should plateau and begin to decline.
2. Switch to the **Overview** tab:
   - C-101 Discharge Temp should drop below 160, then below 155.
   - The colour returns from red → yellow → green.
3. Check the **right panel**:
   - Stability Score rises back toward 90+.
   - Status returns to NORMAL.
   - Recommended Action changes to "No action required — system stable."
4. The alarm clears automatically when temperature drops below 160 °C.

---

## Act 5: Review Log (~15 seconds)

1. Click the **Operator Log** tab.
2. The log shows the full chronological narrative:
   - Scenario loaded
   - Alarms raised
   - Feed rate adjusted
   - Cooling target changed
   - Alarm acknowledged
   - Alarms cleared
   - Stabilisation detected

---

## Optional: Apply Stabilisation Plan

Instead of individual actions, click **✅ Apply Stabilization Plan** in the
right panel. This opens a dialog with checkboxes for all corrective actions.
Check the desired items, enter a justification, and click **Apply Plan**.

---

## Reset

Click **⏹ Reset Demo** to return all values to baseline and try another
scenario (e.g., Scenario 2: Rising Separator Pressure, or Scenario 3: Cooling
Loop Underperformance).
