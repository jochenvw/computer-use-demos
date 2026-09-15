using System.Windows;

namespace plant_manager.Dialogs
{
    public partial class AdjustFeedRateDialog : Window
    {
        public double ResultValue { get; private set; }

        public AdjustFeedRateDialog(double currentValue)
        {
            InitializeComponent();
            CurrentValueText.Text = $"{currentValue:F1} %";
            NewValueBox.Text = currentValue.ToString("F1");
            Loaded += (_, _) =>
            {
                NewValueBox.Focus();
                NewValueBox.SelectAll();
            };
        }

        private void Minus_Click(object sender, RoutedEventArgs e) => Nudge(-5);
        private void Plus_Click(object sender, RoutedEventArgs e) => Nudge(5);

        private void Nudge(double delta)
        {
            if (double.TryParse(NewValueBox.Text, out double current))
            {
                double next = Math.Clamp(current + delta, 50, 110);
                NewValueBox.Text = next.ToString("F1");
                NewValueBox.SelectAll();
            }
        }

        private void Apply_Click(object sender, RoutedEventArgs e)
        {
            if (double.TryParse(NewValueBox.Text, out double val) && val >= 50 && val <= 110)
            {
                ResultValue = val;
                DialogResult = true;
            }
            else
            {
                MessageBox.Show("Please enter a value between 50 and 110.",
                    "Invalid Input", MessageBoxButton.OK, MessageBoxImage.Warning);
            }
        }
    }
}
