using System.Collections.ObjectModel;
using plant_manager.Engine;
using plant_manager.Models;

namespace plant_manager.ViewModels
{
    /// <summary>
    /// Primary ViewModel for the main shell window.
    /// Exposes the simulation engine and commands for the toolbar/menus.
    /// </summary>
    public class MainViewModel : ObservableBase
    {
        public SimulationEngine Engine { get; } = new();

        // ── Navigation ──────────────────────────────────
        private string _selectedAsset = "Facility Overview";
        public string SelectedAsset
        {
            get => _selectedAsset;
            set => SetField(ref _selectedAsset, value);
        }

        private int _selectedTabIndex;
        public int SelectedTabIndex
        {
            get => _selectedTabIndex;
            set => SetField(ref _selectedTabIndex, value);
        }

        // ── Procedure viewer ─────────────────────────────
        private string _selectedProcedureName = "";
        public string SelectedProcedureName
        {
            get => _selectedProcedureName;
            set
            {
                if (SetField(ref _selectedProcedureName, value))
                    OnPropertyChanged(nameof(SelectedProcedureText));
            }
        }

        public string SelectedProcedureText =>
            ProcedureLibrary.Procedures.TryGetValue(SelectedProcedureName, out var text)
                ? text : "Select a procedure from the list above.";

        public List<string> ProcedureNames { get; } = ProcedureLibrary.Procedures.Keys.ToList();

        // ── Derived properties for the right panel ──────
        public string PlantStatusText
        {
            get
            {
                if (Engine.State.StabilityScore > 90) return "NORMAL";
                if (Engine.State.StabilityScore > 70) return "DEGRADED";
                return "ABNORMAL";
            }
        }

        public bool IsDegraded => Engine.State.StabilityScore <= 90;

        public int ActiveAlarmCount => Engine.Alarms.Count(a => a.State == AlarmState.Active);

        public string HighestPriorityAlarm
        {
            get
            {
                var worst = Engine.Alarms
                    .Where(a => a.State == AlarmState.Active)
                    .OrderBy(a => a.Priority)
                    .FirstOrDefault();
                return worst != null ? $"{worst.Tag}: {worst.Description}" : "None";
            }
        }

        public string RecommendedAction
        {
            get
            {
                if (Engine.State.C101DischargeTemp > 160)
                    return "Reduce feed rate by 5%, increase cooling target by 3 °C";
                if (Engine.State.Sep01Pressure > 37)
                    return "Reduce feed rate, verify downstream valve state";
                if (Engine.State.CL01CoolingEfficiency < 85)
                    return "Increase cooling target, check secondary pump";
                return "No action required — system stable";
            }
        }

        // ── Commands ─────────────────────────────────────
        public RelayCommand RefreshCommand { get; }
        public RelayCommand LoadScenario1Command { get; }
        public RelayCommand LoadScenario2Command { get; }
        public RelayCommand LoadScenario3Command { get; }
        public RelayCommand ResetDemoCommand { get; }

        public MainViewModel()
        {
            RefreshCommand = new RelayCommand(_ => RefreshDerived());
            LoadScenario1Command = new RelayCommand(_ => Engine.LoadScenario(ScenarioType.HighDischargeTemp));
            LoadScenario2Command = new RelayCommand(_ => Engine.LoadScenario(ScenarioType.RisingSeparatorPressure));
            LoadScenario3Command = new RelayCommand(_ => Engine.LoadScenario(ScenarioType.CoolingLoopUnderperformance));
            ResetDemoCommand = new RelayCommand(_ => Engine.ResetDemo());

            // Subscribe to timer-driven changes so derived props update
            Engine.State.PropertyChanged += (_, __) => RefreshDerived();
            Engine.Alarms.CollectionChanged += (_, __) => RefreshDerived();

            Engine.Start();
        }

        public void RefreshDerived()
        {
            OnPropertyChanged(nameof(PlantStatusText));
            OnPropertyChanged(nameof(IsDegraded));
            OnPropertyChanged(nameof(ActiveAlarmCount));
            OnPropertyChanged(nameof(HighestPriorityAlarm));
            OnPropertyChanged(nameof(RecommendedAction));
        }
    }
}
