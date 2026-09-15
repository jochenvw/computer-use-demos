using System.Windows;

namespace plant_manager.Dialogs
{
    public partial class SetCoolingTargetDialog : Window
    {
        public double ResultValue { get; private set; }

        public SetCoolingTargetDialog(double currentValue)
        {
            InitializeComponent();
            CurrentValueText.Text = $"{currentValue:F1} °C";
            NewValueBox.Text = currentValue.ToString("F1");
            Loaded += (_, _) =>
            {
                NewValueBox.Focus();
                NewValueBox.SelectAll();
            };
        }

        private void Minus_Click(object sender, RoutedEventArgs e) => Nudge(-3);
        private void Plus_Click(object sender, RoutedEventArgs e) => Nudge(3);

        private void Nudge(double delta)
        {
            if (double.TryParse(NewValueBox.Text, out double current))
            {
                double next = Math.Clamp(current + delta, 25, 50);
                NewValueBox.Text = next.ToString("F1");
                NewValueBox.SelectAll();
            }
        }

        private void Apply_Click(object sender, RoutedEventArgs e)
        {
            if (double.TryParse(NewValueBox.Text, out double val) && val >= 25 && val <= 50)
            {
                ResultValue = val;
                DialogResult = true;
            }
            else
            {
                MessageBox.Show("Please enter a value between 25 and 50.",
                    "Invalid Input", MessageBoxButton.OK, MessageBoxImage.Warning);
            }
        }
    }
}
