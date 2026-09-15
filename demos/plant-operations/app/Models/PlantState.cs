namespace plant_manager.Models
{
    /// <summary>
    /// Holds all live process tag values for the simulated plant.
    /// Values are updated every tick by the SimulationEngine.
    /// </summary>
    public class PlantState : ObservableBase
    {
        // ── Compressor C-101 ─────────────────────────────
        private double _c101DischargeTemp = 142.0;
        public double C101DischargeTemp { get => _c101DischargeTemp; set => SetField(ref _c101DischargeTemp, value); }

        private double _c101SuctionPressure = 48.5;
        public double C101SuctionPressure { get => _c101SuctionPressure; set => SetField(ref _c101SuctionPressure, value); }

        private double _c101Vibration = 2.1;
        public double C101Vibration { get => _c101Vibration; set => SetField(ref _c101Vibration, value); }

        // ── Compressor C-102 ─────────────────────────────
        private double _c102DischargeTemp = 138.0;
        public double C102DischargeTemp { get => _c102DischargeTemp; set => SetField(ref _c102DischargeTemp, value); }

        private double _c102SuctionPressure = 47.2;
        public double C102SuctionPressure { get => _c102SuctionPressure; set => SetField(ref _c102SuctionPressure, value); }

        // ── Separator SEP-01 ─────────────────────────────
        private double _sep01Pressure = 32.0;
        public double Sep01Pressure { get => _sep01Pressure; set => SetField(ref _sep01Pressure, value); }

        private double _sep01Level = 62.0;
        public double Sep01Level { get => _sep01Level; set => SetField(ref _sep01Level, value); }

        // ── Export Pump P-201 ────────────────────────────
        private double _p201FlowRate = 1250.0;
        public double P201FlowRate { get => _p201FlowRate; set => SetField(ref _p201FlowRate, value); }

        // ── Cooling Loop CL-01 ───────────────────────────
        private double _cl01CoolingEfficiency = 94.0;
        public double CL01CoolingEfficiency { get => _cl01CoolingEfficiency; set => SetField(ref _cl01CoolingEfficiency, value); }

        private double _cl01CoolingTarget = 35.0;
        public double CL01CoolingTarget { get => _cl01CoolingTarget; set => SetField(ref _cl01CoolingTarget, value); }

        // ── Flare System ─────────────────────────────────
        private double _flr01ValvePosition = 12.0;
        public double FLR01ValvePosition { get => _flr01ValvePosition; set => SetField(ref _flr01ValvePosition, value); }

        // ── Feed Rate ────────────────────────────────────
        private double _feedRate = 100.0;
        public double FeedRate { get => _feedRate; set => SetField(ref _feedRate, value); }

        // ── Recycle Valve ────────────────────────────────
        private string _recycleValveState = "AUTO";
        public string RecycleValveState { get => _recycleValveState; set => SetField(ref _recycleValveState, value); }

        // ── Production Rate (bbl/d) ──────────────────────
        private double _productionRate = 12400.0;
        public double ProductionRate { get => _productionRate; set => SetField(ref _productionRate, value); }

        // ── Stability Score (0-100) ──────────────────────
        private double _stabilityScore = 96.0;
        public double StabilityScore { get => _stabilityScore; set => SetField(ref _stabilityScore, value); }
    }
}
