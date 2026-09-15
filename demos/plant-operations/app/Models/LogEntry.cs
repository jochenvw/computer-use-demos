namespace plant_manager.Models
{
    /// <summary>
    /// A single entry in the operator log.
    /// </summary>
    public class LogEntry
    {
        public DateTime Timestamp { get; set; }
        public string Category { get; set; } = "";
        public string Message { get; set; } = "";
    }
}
