namespace plant_manager.Models
{
    /// <summary>
    /// Static repository of fake Standard Operating Procedures.
    /// </summary>
    public static class ProcedureLibrary
    {
        public static readonly Dictionary<string, string> Procedures = new()
        {
            ["High Compressor Discharge Temperature"] = @"
═══════════════════════════════════════════════════════════════
  SOP-4017  HIGH COMPRESSOR DISCHARGE TEMPERATURE
  Facility: North Sea Alpha Production Train
  Revision: 3.2   |   Last Updated: 2024-01-15
═══════════════════════════════════════════════════════════════

SYMPTOMS:
  • C-101 or C-102 discharge temperature exceeds 165 °C
  • High-temperature alarm active on compressor panel
  • Possible increase in compressor vibration

LIKELY CAUSES:
  • Elevated feed rate beyond design capacity
  • Cooling loop degradation or fouling
  • Recycle valve stuck in closed position
  • Ambient temperature exceedance

VERIFICATION CHECKS:
  1. Confirm discharge temperature reading on local gauge
  2. Cross-check with redundant sensor (if available)
  3. Check cooling loop outlet temperature
  4. Verify feed rate is within normal range (95-105%)
  5. Confirm recycle valve position (should be AUTO)

SAFE OPERATOR ACTIONS:
  1. Reduce feed rate by 5% using Manual Control dialog
  2. Increase cooling target by 3 °C
  3. Confirm recycle valve is in AUTO mode
  4. Monitor discharge temperature trend for 2 minutes
  5. If temperature stabilizes below 160 °C, maintain settings
  6. If temperature does not decrease, reduce feed rate
     by additional 5% and notify Shift Supervisor

ESCALATION CRITERIA:
  • Temperature exceeds 180 °C — initiate compressor trip
  • Vibration exceeds 8.0 mm/s — emergency shutdown
  • Temperature does not respond within 5 minutes — call
    on-call process engineer

NOTES:
  Always log actions in Operator Log before and after
  adjustments. Do not bypass high-temperature interlock.
═══════════════════════════════════════════════════════════════",

            ["Low Suction Pressure"] = @"
═══════════════════════════════════════════════════════════════
  SOP-4022  LOW SUCTION PRESSURE
  Facility: North Sea Alpha Production Train
  Revision: 2.1   |   Last Updated: 2023-11-08
═══════════════════════════════════════════════════════════════

SYMPTOMS:
  • C-101 suction pressure below 42 barg
  • Low-pressure alarm active
  • Possible compressor surge indication

LIKELY CAUSES:
  • Upstream separator level too low
  • Inlet valve partially closed
  • Pipeline restriction or blockage
  • Loss of well pressure

VERIFICATION CHECKS:
  1. Check SEP-01 vessel pressure and level
  2. Confirm inlet valve position
  3. Verify wellhead pressures (if accessible)
  4. Cross-check flow meter readings

SAFE OPERATOR ACTIONS:
  1. Reduce compressor speed or feed rate by 5%
  2. Check upstream separator level
  3. Verify inlet valve fully open
  4. Monitor suction pressure for 2 minutes
  5. If pressure recovers above 44 barg, return to normal

ESCALATION CRITERIA:
  • Suction pressure below 38 barg — trip compressor
  • Surge detected — immediate shutdown
  • No recovery in 5 minutes — call process engineer
═══════════════════════════════════════════════════════════════",

            ["Rising Separator Pressure"] = @"
═══════════════════════════════════════════════════════════════
  SOP-4031  RISING SEPARATOR PRESSURE
  Facility: North Sea Alpha Production Train
  Revision: 1.8   |   Last Updated: 2024-02-20
═══════════════════════════════════════════════════════════════

SYMPTOMS:
  • SEP-01 vessel pressure rising above 38 barg
  • High-pressure alarm active on separator
  • Possible increase in flare activity

LIKELY CAUSES:
  • Downstream restriction (valve, blockage)
  • Compressor trip or reduced throughput
  • Excess feed rate
  • Gas composition change

VERIFICATION CHECKS:
  1. Confirm SEP-01 pressure on local gauge
  2. Check downstream valve positions
  3. Verify compressor status (running/tripped)
  4. Check flare valve position
  5. Review feed rate trend

SAFE OPERATOR ACTIONS:
  1. Reduce feed rate by 5-10%
  2. Verify downstream outlet valve is fully open
  3. Check compressor is running and not in surge
  4. If flare valve is opening, monitor flare activity
  5. Monitor separator pressure for 3 minutes
  6. If pressure stabilizes below 36 barg, maintain

ESCALATION CRITERIA:
  • Pressure exceeds 42 barg — initiate emergency blowdown
  • Flare valve >80% open — notify Shift Supervisor
  • No response in 5 minutes — call process engineer
═══════════════════════════════════════════════════════════════",

            ["Cooling Loop Underperformance"] = @"
═══════════════════════════════════════════════════════════════
  SOP-4045  COOLING LOOP UNDERPERFORMANCE
  Facility: North Sea Alpha Production Train
  Revision: 2.0   |   Last Updated: 2024-03-10
═══════════════════════════════════════════════════════════════

SYMPTOMS:
  • CL-01 cooling efficiency below 85%
  • Compressor discharge temperatures rising
  • Cooling water outlet temperature elevated

LIKELY CAUSES:
  • Heat exchanger fouling
  • Cooling water pump degradation
  • Ambient temperature exceedance
  • Cooling water supply restriction

VERIFICATION CHECKS:
  1. Check CL-01 cooling efficiency reading
  2. Compare inlet and outlet water temperatures
  3. Verify cooling water pump status
  4. Check for fouling indicators
  5. Review ambient temperature

SAFE OPERATOR ACTIONS:
  1. Increase cooling target setpoint by 3 °C
  2. Check if secondary cooling pump is available
  3. Reduce compressor load by lowering feed rate 5%
  4. Monitor cooling efficiency for 3 minutes
  5. If efficiency recovers above 88%, maintain
  6. Schedule heat exchanger inspection if persistent

ESCALATION CRITERIA:
  • Cooling efficiency below 75% — reduce to minimum load
  • Compressor discharge temp exceeds 175 °C — trip
  • No improvement in 10 minutes — call maintenance
═══════════════════════════════════════════════════════════════"
        };
    }
}
