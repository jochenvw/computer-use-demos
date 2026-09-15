using System.Windows;

namespace plant_manager.Dialogs
{
    public partial class ToggleRecycleDialog : Window
    {
        public ToggleRecycleDialog(string currentState)
        {
            InitializeComponent();
            CurrentStateText.Text = currentState;
        }

        private void Confirm_Click(object sender, RoutedEventArgs e)
        {
            DialogResult = true;
        }
    }
}
