namespace plant_manager.Models
{
    /// <summary>
    /// Represents a single piece of equipment (compressor, pump, etc.).
    /// </summary>
    public class EquipmentItem : ObservableBase
    {
        private string _mode = "AUTO";
        private string _healthState = "Normal";
        private string _runState = "Running";
        private double _currentOutput;
        private double _currentSetpoint;
        private bool _manualOverride;

        public string Name { get; set; } = "";
        public string TagPrefix { get; set; } = "";

        public string Mode { get => _mode; set => SetField(ref _mode, value); }
        public string HealthState { get => _healthState; set => SetField(ref _healthState, value); }
        public string RunState { get => _runState; set => SetField(ref _runState, value); }
        public string LastInspection { get; set; } = "";
        public string MaintenanceNote { get; set; } = "";
        public double CurrentSetpoint { get => _currentSetpoint; set => SetField(ref _currentSetpoint, value); }
        public double CurrentOutput { get => _currentOutput; set => SetField(ref _currentOutput, value); }
        public bool ManualOverride { get => _manualOverride; set => SetField(ref _manualOverride, value); }
    }
}
