using System.Windows;
using System.Windows.Controls;
using LiveChartsCore;
using LiveChartsCore.Defaults;
using LiveChartsCore.SkiaSharpView;
using LiveChartsCore.SkiaSharpView.Painting;
using plant_manager.Dialogs;
using plant_manager.Models;
using plant_manager.ViewModels;
using SkiaSharp;

namespace plant_manager
{
    /// <summary>
    /// Main shell window for the Plant Manager application.
    /// Wires up the ViewModel, chart series, and toolbar/dialog event handlers.
    /// </summary>
    public partial class MainWindow : Window
    {
        private readonly MainViewModel _vm;

        // Observable collections that LiveCharts watches for trend updates
        private readonly List<ObservableValue> _tempValues = new();
        private readonly List<ObservableValue> _pressValues = new();
        private readonly List<ObservableValue> _flowValues = new();

        public MainWindow()
        {
            InitializeComponent();

            _vm = new MainViewModel();
            DataContext = _vm;

            SetupCharts();

            // Sync chart data every second from the engine trend buffers
            var chartTimer = new System.Windows.Threading.DispatcherTimer
            {
                Interval = TimeSpan.FromSeconds(1)
            };
            chartTimer.Tick += (_, _) => RefreshChartData();
            chartTimer.Start();
        }

        // ── Chart setup ──────────────────────────────────
        private void SetupCharts()
        {
            // Seed initial values
            foreach (var v in _vm.Engine.TrendDischargeTemp) _tempValues.Add(new ObservableValue(v));
            foreach (var v in _vm.Engine.TrendSepPressure) _pressValues.Add(new ObservableValue(v));
            foreach (var v in _vm.Engine.TrendFlowRate) _flowValues.Add(new ObservableValue(v));

            ChartTemp.Series = new ISeries[]
            {
                new LineSeries<ObservableValue>
                {
                    Values = _tempValues,
                    GeometrySize = 0,
                    Stroke = new SolidColorPaint(SKColors.OrangeRed, 2),
                    Fill = null,
                    LineSmoothness = 0.3
                }
            };

            ChartPressure.Series = new ISeries[]
            {
                new LineSeries<ObservableValue>
                {
                    Values = _pressValues,
                    GeometrySize = 0,
                    Stroke = new SolidColorPaint(SKColors.SteelBlue, 2),
                    Fill = null,
                    LineSmoothness = 0.3
                }
            };

            ChartFlow.Series = new ISeries[]
            {
                new LineSeries<ObservableValue>
                {
                    Values = _flowValues,
                    GeometrySize = 0,
                    Stroke = new SolidColorPaint(SKColors.ForestGreen, 2),
                    Fill = null,
                    LineSmoothness = 0.3
                }
            };

            // Minimal axis styling for "legacy" look
            var xAxis = new Axis { IsVisible = false };
            ChartTemp.XAxes = new[] { xAxis };
            ChartPressure.XAxes = new[] { new Axis { IsVisible = false } };
            ChartFlow.XAxes = new[] { new Axis { IsVisible = false } };
        }

        private void RefreshChartData()
        {
            SyncCollection(_tempValues, _vm.Engine.TrendDischargeTemp);
            SyncCollection(_pressValues, _vm.Engine.TrendSepPressure);
            SyncCollection(_flowValues, _vm.Engine.TrendFlowRate);
        }

        private static void SyncCollection(List<ObservableValue> target,
            System.Collections.ObjectModel.ObservableCollection<double> source)
        {
            // Keep lists the same length, update values in place for performance
            while (target.Count > source.Count) target.RemoveAt(0);
            while (target.Count < source.Count) target.Add(new ObservableValue(0));
            for (int i = 0; i < source.Count; i++)
                target[i].Value = source[i];
        }

        // ── Toolbar button handlers ──────────────────────
        private void AcknowledgeAlarm_Click(object sender, RoutedEventArgs e)
        {
            var alarm = AlarmGrid.SelectedItem as AlarmEntry
                ?? _vm.Engine.Alarms.FirstOrDefault(a => a.State == AlarmState.Active);
            if (alarm == null || alarm.State != AlarmState.Active)
            {
                MessageBox.Show("No active alarm selected.", "Acknowledge Alarm",
                    MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }

            var dlg = new AcknowledgeAlarmDialog(alarm.Tag, alarm.Description) { Owner = this };
            if (dlg.ShowDialog() == true)
            {
                _vm.Engine.AcknowledgeAlarm(alarm, dlg.ResultNotes);
            }
        }

        private void OpenProcedure_Click(object sender, RoutedEventArgs e)
        {
            // Switch to Procedures tab
            _vm.SelectedTabIndex = 4;
        }

        private void TrendView_Click(object sender, RoutedEventArgs e)
        {
            _vm.SelectedTabIndex = 2;
        }

        private void AssetDetails_Click(object sender, RoutedEventArgs e)
        {
            _vm.SelectedTabIndex = 3;
        }

        private void ManualControl_Click(object sender, RoutedEventArgs e)
        {
            // Open a sub-menu of manual controls
            var menu = new ContextMenu();
            var mi1 = new MenuItem { Header = "Adjust Feed Rate" };
            mi1.Click += AdjustFeedRate_Click;
            var mi2 = new MenuItem { Header = "Set Cooling Target" };
            mi2.Click += SetCoolingTarget_Click;
            var mi3 = new MenuItem { Header = "Toggle Recycle Valve" };
            mi3.Click += ToggleRecycleValve_Click;
            var mi4 = new MenuItem { Header = "Apply Stabilization Plan" };
            mi4.Click += ApplyStabilization_Click;
            menu.Items.Add(mi1);
            menu.Items.Add(mi2);
            menu.Items.Add(mi3);
            menu.Items.Add(new Separator());
            menu.Items.Add(mi4);
            menu.IsOpen = true;
        }

        private void IncidentSummary_Click(object sender, RoutedEventArgs e)
        {
            _vm.SelectedTabIndex = 5; // Operator Log tab
        }

        // ── Alarm toolbar buttons ────────────────────────
        private void ShelveAlarm_Click(object sender, RoutedEventArgs e)
        {
            var alarm = AlarmGrid.SelectedItem as AlarmEntry;
            if (alarm == null)
            {
                MessageBox.Show("Select an alarm to shelve.", "Shelve Alarm",
                    MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }
            if (MessageBox.Show($"Shelve alarm {alarm.Tag}?", "Confirm Shelve",
                    MessageBoxButton.YesNo, MessageBoxImage.Question) == MessageBoxResult.Yes)
            {
                _vm.Engine.ShelveAlarm(alarm);
            }
        }

        private void OpenRelatedProcedure_Click(object sender, RoutedEventArgs e)
        {
            var alarm = AlarmGrid.SelectedItem as AlarmEntry;
            if (alarm == null) return;

            // Map alarm tags to procedures
            string? proc = null;
            if (alarm.Tag.Contains("DTEMP")) proc = "High Compressor Discharge Temperature";
            else if (alarm.Tag.Contains("PRESS")) proc = "Rising Separator Pressure";
            else if (alarm.Tag.Contains("EFF")) proc = "Cooling Loop Underperformance";
            else if (alarm.Tag.Contains("SUCT")) proc = "Low Suction Pressure";

            if (proc != null)
            {
                _vm.SelectedProcedureName = proc;
                _vm.SelectedTabIndex = 4;
                _vm.Engine.AddLog("OPERATOR", $"Opened procedure: {proc}");
            }
            else
            {
                MessageBox.Show("No related procedure found for this alarm.",
                    "Procedures", MessageBoxButton.OK, MessageBoxImage.Information);
            }
        }

        private void ShowAsset_Click(object sender, RoutedEventArgs e)
        {
            var alarm = AlarmGrid.SelectedItem as AlarmEntry;
            if (alarm == null) return;
            _vm.SelectedTabIndex = 3; // Equipment tab
        }

        // ── Manual control dialogs ───────────────────────
        private void AdjustFeedRate_Click(object sender, RoutedEventArgs e)
        {
            var dlg = new AdjustFeedRateDialog(_vm.Engine.State.FeedRate) { Owner = this };
            if (dlg.ShowDialog() == true)
            {
                _vm.Engine.AdjustFeedRate(dlg.ResultValue);
            }
        }

        private void SetCoolingTarget_Click(object sender, RoutedEventArgs e)
        {
            var dlg = new SetCoolingTargetDialog(_vm.Engine.State.CL01CoolingTarget) { Owner = this };
            if (dlg.ShowDialog() == true)
            {
                _vm.Engine.SetCoolingTarget(dlg.ResultValue);
            }
        }

        private void ToggleRecycleValve_Click(object sender, RoutedEventArgs e)
        {
            var dlg = new ToggleRecycleDialog(_vm.Engine.State.RecycleValveState) { Owner = this };
            if (dlg.ShowDialog() == true)
            {
                _vm.Engine.ToggleRecycleMode();
            }
        }

        private void ApplyStabilization_Click(object sender, RoutedEventArgs e)
        {
            var dlg = new StabilizationPlanDialog { Owner = this };
            if (dlg.ShowDialog() == true)
            {
                if (dlg.ApplyFeedRate) _vm.Engine.AdjustFeedRate(_vm.Engine.State.FeedRate - 5);
                if (dlg.ApplyCooling) _vm.Engine.SetCoolingTarget(_vm.Engine.State.CL01CoolingTarget + 3);
                if (dlg.ApplyRecycle && _vm.Engine.State.RecycleValveState != "AUTO")
                    _vm.Engine.ToggleRecycleMode();
                if (dlg.AckAlarms)
                {
                    foreach (var alarm in _vm.Engine.Alarms.Where(a => a.State == AlarmState.Active).ToList())
                        _vm.Engine.AcknowledgeAlarm(alarm, "Stabilization plan applied");
                }
                _vm.Engine.AddLog("OPERATOR", $"Stabilization plan applied — {dlg.Justification}");
            }
        }
    }
}