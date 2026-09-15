using System.Windows;

namespace plant_manager.Dialogs
{
    public partial class StabilizationPlanDialog : Window
    {
        public bool ApplyFeedRate => ChkFeedRate.IsChecked == true;
        public bool ApplyCooling => ChkCooling.IsChecked == true;
        public bool ApplyRecycle => ChkRecycle.IsChecked == true;
        public bool AckAlarms => ChkAckAlarms.IsChecked == true;
        public string Justification => JustificationBox.Text;

        public StabilizationPlanDialog()
        {
            InitializeComponent();
        }

        private void Apply_Click(object sender, RoutedEventArgs e)
        {
            if (string.IsNullOrWhiteSpace(JustificationBox.Text))
            {
                MessageBox.Show("Please provide an operator justification.",
                    "Required Field", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }
            DialogResult = true;
        }
    }
}
