# Plant Operations Computer-Use Demo

A fake "legacy" plant operations desktop application and companion computer-use
agent. The simulator is built with WPF on .NET 8; the Python agent uses Azure AI
Foundry computer use.

This demo is synthetic and must never be connected to real industrial controls.

## How to Run

1. From the repository root, run:

   ```powershell
   dotnet run --project .\demos\plant-operations\app\plant_manager.csproj
   ```

   Alternatively, open `computer-use-demos.slnx` in Visual Studio and press
   **F5**.
2. The simulation starts automatically — live telemetry values update every second.

The simulator has no database or network access. It uses LiveCharts2 for local
trend charts.

## Run the agent

```powershell
cd .\demos\plant-operations\agent
uv sync --locked --default-index https://pypi.org/simple
$env:AZURE_AI_FOUNDRY_ENDPOINT = "https://your-resource.services.ai.azure.com"

# Safe default: model observes and proposes actions without clicking
uv run --frozen python main.py --once

# Explicitly enable local simulator control
$env:ALLOW_COMPUTER_CONTROL = "1"
uv run --frozen python main.py --once --live
```

The agent aborts unless the exact
`North Sea Alpha — Plant Manager v4.7.2 [SIMULATION MODE]` window is present.

## Project Structure

```
app/
├── Models/
│   ├── ObservableBase.cs      MVVM base + RelayCommand
│   ├── PlantState.cs          Live process tag values
│   ├── AlarmEntry.cs          Alarm data model
│   ├── EquipmentItem.cs       Equipment card model
│   ├── LogEntry.cs            Operator log entry
│   └── ProcedureLibrary.cs    Fake SOPs (4 procedures)
├── Engine/
│   └── SimulationEngine.cs    Telemetry generator + 3 scenarios
├── ViewModels/
│   └── MainViewModel.cs       Shell ViewModel
├── Converters/
│   └── ValueConverters.cs     Colour/visibility converters
├── Dialogs/
│   ├── AdjustFeedRateDialog    Feed rate manual control
│   ├── SetCoolingTargetDialog  Cooling target adjustment
│   ├── ToggleRecycleDialog     Recycle valve toggle
│   ├── AcknowledgeAlarmDialog  Alarm acknowledgement
│   └── StabilizationPlanDialog Multi-action corrective plan
├── MainWindow.xaml / .cs       Shell window (toolbar, tabs, panels)
└── App.xaml / .cs              Application entry
```

## Triggering Scenarios

Use the **toolbar buttons** at the top of the window:

| Button | Scenario |
|--------|----------|
| ▶ Scenario 1: High Temp | C-101 discharge temperature rises over ~30 seconds |
| ▶ Scenario 2: Sep Press | SEP-01 vessel pressure climbs over ~25 seconds |
| ▶ Scenario 3: Cooling | CL-01 cooling efficiency degrades, causing downstream temp rise |
| ⏹ Reset Demo | Returns all values to baseline and clears scenario alarms |

## How the Simulation Works

- A `DispatcherTimer` ticks once per second.
- Each tick advances simulated time by 10 seconds (accelerated).
- Scenario effects (temperature ramp, pressure drift, etc.) are applied for a
  fixed number of ticks, then the scenario waits for operator action.
- Operator actions (reduce feed rate, increase cooling, toggle recycle valve)
  feed back into the state via simple coefficients.
- A slow mean-reversion pulls all values back toward their nominal baseline.
- Random noise is added each tick for realism.
- Alarm conditions are checked every tick: alarms are raised when thresholds
  are crossed and cleared when values recover.
- The stability score is a simple weighted deviation from nominal values.

## Key UI Areas

- **Overview tab**: Live process values with colour-coded indicators
- **Alarms tab**: DataGrid with Acknowledge / Shelve / Open Procedure buttons
- **Trends tab**: Three live line charts (temperature, pressure, flow)
- **Equipment tab**: Equipment cards with health state
- **Procedures tab**: Full-text SOP viewer (dropdown to select)
- **Operator Log tab**: Chronological log of all actions and events
- **Right panel**: Plant status summary, recommended actions, quick controls
- **Status bar**: Simulated time, operator name, alarm count, comm status
