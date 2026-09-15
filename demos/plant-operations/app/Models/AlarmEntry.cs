namespace plant_manager.Models
{
    public enum AlarmPriority { Critical, Warning, Advisory }
    public enum AlarmState { Active, Acknowledged, Cleared, Shelved }

    /// <summary>
    /// Represents a single alarm event in the plant alarm system.
    /// </summary>
    public class AlarmEntry : ObservableBase
    {
        private AlarmState _state;
        private string _acknowledgedBy = "";
        private string _notes = "";

        public DateTime Timestamp { get; set; }
        public AlarmPriority Priority { get; set; }
        public string Asset { get; set; } = "";
        public string Tag { get; set; } = "";
        public string Description { get; set; } = "";

        public AlarmState State
        {
            get => _state;
            set => SetField(ref _state, value);
        }

        public string AcknowledgedBy
        {
            get => _acknowledgedBy;
            set => SetField(ref _acknowledgedBy, value);
        }

        public string Notes
        {
            get => _notes;
            set => SetField(ref _notes, value);
        }
    }
}
