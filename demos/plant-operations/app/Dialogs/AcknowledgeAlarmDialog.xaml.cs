using System.Windows;

namespace plant_manager.Dialogs
{
    public partial class AcknowledgeAlarmDialog : Window
    {
        public string ResultNotes { get; private set; } = "";

        public AcknowledgeAlarmDialog(string tag, string description)
        {
            InitializeComponent();
            AlarmTagText.Text = tag;
            AlarmDescText.Text = description;
            NotesBox.Focus();
        }

        private void Confirm_Click(object sender, RoutedEventArgs e)
        {
            ResultNotes = NotesBox.Text;
            DialogResult = true;
        }
    }
}
