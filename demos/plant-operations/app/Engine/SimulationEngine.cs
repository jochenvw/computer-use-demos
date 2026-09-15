using System.Collections.ObjectModel;
using System.Windows.Threading;
using plant_manager.Models;

namespace plant_manager.Engine
{
    public enum ScenarioType { None, HighDischargeTemp, RisingSeparatorPressure, CoolingLoopUnderperformance }

    /// <summary>
    /// Drives the fake telemetry and scenario state machine.
    /// Ticks every second, updates PlantState, raises alarms, etc.
    /// </summary>
    public class SimulationEngine : ObservableBase
    {
        private readonly DispatcherTimer _timer;
        private readonly Random _rng = new(42);
        private int _tickCount;

        public PlantState State { get; } = new();
        public ObservableCollection<AlarmEntry> Alarms { get; } = new();
        public ObservableCollection<LogEntry> OperatorLog { get; } = new();
        public ObservableCollection<EquipmentItem> Equipment { get; } = new();

        // Trend history (last 120 data points ≈ 2 minutes)
        public ObservableCollection<double> TrendDischargeTemp { get; } = new();
        public ObservableCollection<double> TrendSepPressure { get; } = new();
        public ObservableCollection<double> TrendFlowRate { get; } = new();

        private ScenarioType _activeScenario = ScenarioType.None;
        public ScenarioType ActiveScenario
        {
            get => _activeScenario;
            private set => SetField(ref _activeScenario, value);
        }

        private string _scenarioStatus = "Idle";
        public string ScenarioStatus
        {
            get => _scenarioStatus;
            set => SetField(ref _scenarioStatus, value);
        }

        private DateTime _simTime;
        public DateTime SimTime
        {
            get => _simTime;
            set => SetField(ref _simTime, value);
        }

        public SimulationEngine()
        {
            SimTime = new DateTime(2025, 6, 14, 6, 0, 0);

            InitEquipment();

            _timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
            _timer.Tick += OnTick;

            // Seed trend history
            for (int i = 0; i < 60; i++)
            {
                TrendDischargeTemp.Add(142 + Noise(0.5));
                TrendSepPressure.Add(32 + Noise(0.3));
                TrendFlowRate.Add(1250 + Noise(5));
            }

            AddLog("SYSTEM", "Simulation engine initialized — North Sea Alpha Production Train");
            AddLog("SYSTEM", "Operator J. Hansen logged in");

            // Seed a mild advisory alarm
            Alarms.Add(new AlarmEntry
            {
                Timestamp = SimTime.AddMinutes(-12),
                Priority = AlarmPriority.Advisory,
                Asset = "P-201",
                Tag = "P201-VIB-HI",
                Description = "Export pump vibration marginally elevated",
                State = AlarmState.Active
            });
        }

        public void Start() => _timer.Start();
        public void Stop() => _timer.Stop();

        // ── Scenario trigger ─────────────────────────────
        public void LoadScenario(ScenarioType scenario)
        {
            ResetState();
            ActiveScenario = scenario;
            _tickCount = 0;

            switch (scenario)
            {
                case ScenarioType.HighDischargeTemp:
                    ScenarioStatus = "Scenario: High Discharge Temp — ramping";
                    AddLog("SCENARIO", "Demo scenario loaded: High Compressor Discharge Temperature");
                    break;
                case ScenarioType.RisingSeparatorPressure:
                    ScenarioStatus = "Scenario: Rising Sep Pressure — ramping";
                    AddLog("SCENARIO", "Demo scenario loaded: Rising Separator Pressure");
                    break;
                case ScenarioType.CoolingLoopUnderperformance:
                    ScenarioStatus = "Scenario: Cooling Loop Underperformance — ramping";
                    AddLog("SCENARIO", "Demo scenario loaded: Cooling Loop Underperformance");
                    break;
            }
        }

        public void ResetDemo()
        {
            ResetState();
            ActiveScenario = ScenarioType.None;
            ScenarioStatus = "Idle";
            _tickCount = 0;

            // Clear scenario alarms but keep the seed advisory
            for (int i = Alarms.Count - 1; i >= 0; i--)
            {
                if (Alarms[i].Tag != "P201-VIB-HI")
                    Alarms.RemoveAt(i);
            }

            AddLog("SYSTEM", "Demo reset — all values returned to baseline");
        }

        // ── Manual operator actions (called from dialogs) ─
        public void AdjustFeedRate(double newPercent)
        {
            State.FeedRate = Math.Clamp(newPercent, 50, 110);
            AddLog("OPERATOR", $"Feed rate adjusted to {State.FeedRate:F1}%");
        }

        public void SetCoolingTarget(double newTarget)
        {
            State.CL01CoolingTarget = Math.Clamp(newTarget, 25, 50);
            AddLog("OPERATOR", $"Cooling target set to {State.CL01CoolingTarget:F1} °C");
        }

        public void ToggleRecycleMode()
        {
            State.RecycleValveState = State.RecycleValveState == "AUTO" ? "MANUAL-OPEN" : "AUTO";
            AddLog("OPERATOR", $"Recycle valve set to {State.RecycleValveState}");
        }

        public void AcknowledgeAlarm(AlarmEntry alarm, string note)
        {
            alarm.State = AlarmState.Acknowledged;
            alarm.AcknowledgedBy = "J. Hansen";
            alarm.Notes = note;
            AddLog("OPERATOR", $"Alarm acknowledged: {alarm.Tag} — {note}");
        }

        public void ShelveAlarm(AlarmEntry alarm)
        {
            alarm.State = AlarmState.Shelved;
            AddLog("OPERATOR", $"Alarm shelved: {alarm.Tag}");
        }

        public void AddLog(string category, string message)
        {
            OperatorLog.Insert(0, new LogEntry
            {
                Timestamp = SimTime,
                Category = category,
                Message = message
            });
        }

        // ── Tick handler ─────────────────────────────────
        private void OnTick(object? sender, EventArgs e)
        {
            _tickCount++;
            SimTime = SimTime.AddSeconds(10); // sim time runs 10x

            // Apply scenario effects
            switch (ActiveScenario)
            {
                case ScenarioType.HighDischargeTemp:
                    TickHighDischargeTemp();
                    break;
                case ScenarioType.RisingSeparatorPressure:
                    TickRisingSepPressure();
                    break;
                case ScenarioType.CoolingLoopUnderperformance:
                    TickCoolingLoop();
                    break;
            }

            // Apply natural damping from operator corrections
            ApplyFeedbackEffects();

            // Add noise to readings
            State.C101DischargeTemp += Noise(0.3);
            State.C101SuctionPressure += Noise(0.1);
            State.Sep01Pressure += Noise(0.1);
            State.P201FlowRate += Noise(2);
            State.C101Vibration += Noise(0.05);
            State.Sep01Level += Noise(0.2);

            // Clamp values
            State.C101DischargeTemp = Math.Max(100, State.C101DischargeTemp);
            State.C101SuctionPressure = Math.Max(30, State.C101SuctionPressure);
            State.Sep01Pressure = Math.Max(20, State.Sep01Pressure);
            State.P201FlowRate = Math.Max(500, State.P201FlowRate);
            State.CL01CoolingEfficiency = Math.Clamp(State.CL01CoolingEfficiency, 50, 99);
            State.C101Vibration = Math.Max(0.5, State.C101Vibration);

            // Update derived values
            State.ProductionRate = 12400 * (State.FeedRate / 100.0) + Noise(20);
            UpdateStabilityScore();
            UpdateEquipmentFromState();

            // Push trend data
            TrendDischargeTemp.Add(State.C101DischargeTemp);
            TrendSepPressure.Add(State.Sep01Pressure);
            TrendFlowRate.Add(State.P201FlowRate);
            if (TrendDischargeTemp.Count > 120) TrendDischargeTemp.RemoveAt(0);
            if (TrendSepPressure.Count > 120) TrendSepPressure.RemoveAt(0);
            if (TrendFlowRate.Count > 120) TrendFlowRate.RemoveAt(0);

            // Check alarm conditions
            CheckAlarms();
        }

        // ── Scenario: High discharge temperature ─────────
        private void TickHighDischargeTemp()
        {
            if (_tickCount < 30) // ramp up for ~30 seconds
            {
                State.C101DischargeTemp += 1.2;
                ScenarioStatus = "Scenario: High Discharge Temp — temperature rising";
            }
            else
            {
                ScenarioStatus = "Scenario: High Discharge Temp — awaiting operator action";
            }
        }

        // ── Scenario: Rising separator pressure ──────────
        private void TickRisingSepPressure()
        {
            if (_tickCount < 25)
            {
                State.Sep01Pressure += 0.4;
                ScenarioStatus = "Scenario: Rising Sep Pressure — pressure climbing";
            }
            else
            {
                ScenarioStatus = "Scenario: Rising Sep Pressure — awaiting operator action";
            }
        }

        // ── Scenario: Cooling loop underperformance ──────
        private void TickCoolingLoop()
        {
            if (_tickCount < 20)
            {
                State.CL01CoolingEfficiency -= 0.6;
                // cooling degradation causes downstream temp rise
                State.C101DischargeTemp += 0.5;
                ScenarioStatus = "Scenario: Cooling Loop — efficiency degrading";
            }
            else
            {
                ScenarioStatus = "Scenario: Cooling Loop — awaiting operator action";
            }
        }

        // ── Feedback from operator actions ───────────────
        private void ApplyFeedbackEffects()
        {
            // Lower feed rate reduces temperature and pressure
            double feedDelta = (State.FeedRate - 100.0) / 100.0;
            State.C101DischargeTemp += feedDelta * 0.8;
            State.Sep01Pressure += feedDelta * 0.3;

            // Higher cooling target reduces discharge temp
            double coolDelta = (State.CL01CoolingTarget - 35.0);
            if (coolDelta > 0)
            {
                State.C101DischargeTemp -= coolDelta * 0.15;
                State.CL01CoolingEfficiency += coolDelta * 0.05;
            }

            // Recycle valve in MANUAL-OPEN helps relieve pressure
            if (State.RecycleValveState == "MANUAL-OPEN")
            {
                State.Sep01Pressure -= 0.15;
                State.C101DischargeTemp -= 0.1;
            }

            // Natural mean-reversion (slow drift back to normal)
            State.C101DischargeTemp += (142.0 - State.C101DischargeTemp) * 0.005;
            State.Sep01Pressure += (32.0 - State.Sep01Pressure) * 0.005;
            State.CL01CoolingEfficiency += (94.0 - State.CL01CoolingEfficiency) * 0.003;
            State.P201FlowRate += (1250.0 - State.P201FlowRate) * 0.01;
        }

        private void UpdateStabilityScore()
        {
            double score = 100;
            // Penalise deviations from normal
            score -= Math.Abs(State.C101DischargeTemp - 142) * 0.5;
            score -= Math.Abs(State.Sep01Pressure - 32) * 1.0;
            score -= Math.Abs(State.CL01CoolingEfficiency - 94) * 0.3;
            score -= Math.Abs(State.FeedRate - 100) * 0.2;
            State.StabilityScore = Math.Clamp(score, 0, 100);
        }

        // ── Alarm checks ────────────────────────────────
        private void CheckAlarms()
        {
            // High discharge temp
            CheckOrRaiseAlarm(State.C101DischargeTemp > 165,
                "C-101", "C101-DTEMP-HH", "C-101 discharge temperature HIGH HIGH",
                State.C101DischargeTemp <= 160,
                AlarmPriority.Critical);

            CheckOrRaiseAlarm(State.C101DischargeTemp > 155 && State.C101DischargeTemp <= 165,
                "C-101", "C101-DTEMP-HI", "C-101 discharge temperature HIGH",
                State.C101DischargeTemp <= 150,
                AlarmPriority.Warning);

            // Rising separator pressure
            CheckOrRaiseAlarm(State.Sep01Pressure > 40,
                "SEP-01", "SEP01-PRESS-HH", "SEP-01 vessel pressure HIGH HIGH",
                State.Sep01Pressure <= 37,
                AlarmPriority.Critical);

            CheckOrRaiseAlarm(State.Sep01Pressure > 36 && State.Sep01Pressure <= 40,
                "SEP-01", "SEP01-PRESS-HI", "SEP-01 vessel pressure HIGH",
                State.Sep01Pressure <= 34,
                AlarmPriority.Warning);

            // Cooling efficiency
            CheckOrRaiseAlarm(State.CL01CoolingEfficiency < 80,
                "CL-01", "CL01-EFF-LO", "CL-01 cooling efficiency LOW",
                State.CL01CoolingEfficiency >= 85,
                AlarmPriority.Warning);
        }

        private void CheckOrRaiseAlarm(bool triggerCondition, string asset, string tag,
            string description, bool clearCondition, AlarmPriority priority)
        {
            var existing = FindAlarm(tag);

            if (triggerCondition && existing == null)
            {
                var alarm = new AlarmEntry
                {
                    Timestamp = SimTime,
                    Priority = priority,
                    Asset = asset,
                    Tag = tag,
                    Description = description,
                    State = AlarmState.Active
                };
                Alarms.Insert(0, alarm);
                AddLog("ALARM", $"Alarm raised: {tag} — {description}");
            }
            else if (clearCondition && existing != null &&
                     existing.State is AlarmState.Active or AlarmState.Acknowledged)
            {
                existing.State = AlarmState.Cleared;
                AddLog("ALARM", $"Alarm cleared: {tag}");
            }
        }

        private AlarmEntry? FindAlarm(string tag)
            => Alarms.FirstOrDefault(a => a.Tag == tag && a.State is AlarmState.Active or AlarmState.Acknowledged);

        // ── Equipment helper ─────────────────────────────
        private void InitEquipment()
        {
            Equipment.Add(new EquipmentItem
            {
                Name = "Compressor C-101", TagPrefix = "C-101",
                LastInspection = "2025-04-22", MaintenanceNote = "Bearings replaced Q1 2025",
                CurrentSetpoint = 145, CurrentOutput = 142, Mode = "AUTO"
            });
            Equipment.Add(new EquipmentItem
            {
                Name = "Compressor C-102", TagPrefix = "C-102",
                LastInspection = "2025-03-15", MaintenanceNote = "No issues noted",
                CurrentSetpoint = 140, CurrentOutput = 138, Mode = "AUTO"
            });
            Equipment.Add(new EquipmentItem
            {
                Name = "Separator SEP-01", TagPrefix = "SEP-01",
                LastInspection = "2025-05-01", MaintenanceNote = "Level transmitter calibrated",
                CurrentSetpoint = 32, CurrentOutput = 32, Mode = "AUTO"
            });
            Equipment.Add(new EquipmentItem
            {
                Name = "Export Pump P-201", TagPrefix = "P-201",
                LastInspection = "2025-02-28", MaintenanceNote = "Impeller wear noted — monitor",
                CurrentSetpoint = 1250, CurrentOutput = 1250, Mode = "AUTO"
            });
            Equipment.Add(new EquipmentItem
            {
                Name = "Cooling Loop CL-01", TagPrefix = "CL-01",
                LastInspection = "2025-05-10", MaintenanceNote = "Heat exchanger fouling trending up",
                CurrentSetpoint = 35, CurrentOutput = 94, Mode = "AUTO"
            });
            Equipment.Add(new EquipmentItem
            {
                Name = "Flare System FLR-01", TagPrefix = "FLR-01",
                LastInspection = "2025-01-20", MaintenanceNote = "Pilot flame inspected OK",
                CurrentSetpoint = 0, CurrentOutput = 12, Mode = "AUTO"
            });
        }

        private void UpdateEquipmentFromState()
        {
            foreach (var eq in Equipment)
            {
                switch (eq.TagPrefix)
                {
                    case "C-101":
                        eq.CurrentOutput = Math.Round(State.C101DischargeTemp, 1);
                        eq.HealthState = State.C101DischargeTemp > 165 ? "WARNING" :
                                         State.C101DischargeTemp > 155 ? "Elevated" : "Normal";
                        break;
                    case "C-102":
                        eq.CurrentOutput = Math.Round(State.C102DischargeTemp, 1);
                        break;
                    case "SEP-01":
                        eq.CurrentOutput = Math.Round(State.Sep01Pressure, 1);
                        eq.HealthState = State.Sep01Pressure > 40 ? "WARNING" :
                                         State.Sep01Pressure > 36 ? "Elevated" : "Normal";
                        break;
                    case "P-201":
                        eq.CurrentOutput = Math.Round(State.P201FlowRate, 0);
                        break;
                    case "CL-01":
                        eq.CurrentOutput = Math.Round(State.CL01CoolingEfficiency, 1);
                        eq.HealthState = State.CL01CoolingEfficiency < 80 ? "WARNING" :
                                         State.CL01CoolingEfficiency < 88 ? "Degraded" : "Normal";
                        break;
                    case "FLR-01":
                        eq.CurrentOutput = Math.Round(State.FLR01ValvePosition, 1);
                        break;
                }
            }
        }

        private void ResetState()
        {
            State.C101DischargeTemp = 142;
            State.C101SuctionPressure = 48.5;
            State.C101Vibration = 2.1;
            State.C102DischargeTemp = 138;
            State.C102SuctionPressure = 47.2;
            State.Sep01Pressure = 32;
            State.Sep01Level = 62;
            State.P201FlowRate = 1250;
            State.CL01CoolingEfficiency = 94;
            State.CL01CoolingTarget = 35;
            State.FLR01ValvePosition = 12;
            State.FeedRate = 100;
            State.RecycleValveState = "AUTO";
            State.ProductionRate = 12400;
            State.StabilityScore = 96;
        }

        private double Noise(double scale) => (_rng.NextDouble() - 0.5) * 2 * scale;
    }
}
