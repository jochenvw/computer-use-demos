using System.Globalization;
using System.Windows;
using System.Windows.Data;
using System.Windows.Media;
using plant_manager.Models;

namespace plant_manager.Converters
{
    /// <summary>Alarm priority → background color for grid rows.</summary>
    public class AlarmPriorityToColorConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            if (value is AlarmPriority p)
            {
                return p switch
                {
                    AlarmPriority.Critical => new SolidColorBrush(Color.FromRgb(255, 80, 80)),
                    AlarmPriority.Warning => new SolidColorBrush(Color.FromRgb(255, 220, 80)),
                    _ => new SolidColorBrush(Color.FromRgb(200, 200, 200))
                };
            }
            return Brushes.Transparent;
        }
        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
            => throw new NotImplementedException();
    }

    /// <summary>Alarm state → row opacity (cleared = faded).</summary>
    public class AlarmStateToOpacityConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
            => value is AlarmState s && s == AlarmState.Cleared ? 0.5 : 1.0;
        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
            => throw new NotImplementedException();
    }

    /// <summary>Stability score → colour (green/yellow/red).</summary>
    public class StabilityScoreToColorConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            if (value is double d)
            {
                if (d > 90) return new SolidColorBrush(Color.FromRgb(0, 180, 0));
                if (d > 70) return new SolidColorBrush(Color.FromRgb(200, 180, 0));
                return new SolidColorBrush(Color.FromRgb(220, 40, 40));
            }
            return Brushes.Gray;
        }
        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
            => throw new NotImplementedException();
    }

    /// <summary>Value > threshold → red foreground.</summary>
    public class HighTempToColorConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            if (value is double d)
            {
                if (d > 165) return Brushes.Red;
                if (d > 155) return new SolidColorBrush(Color.FromRgb(200, 140, 0));
            }
            return new SolidColorBrush(Color.FromRgb(0, 160, 0));
        }
        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
            => throw new NotImplementedException();
    }

    /// <summary>Pressure > threshold → colour.</summary>
    public class HighPressureToColorConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            if (value is double d)
            {
                if (d > 40) return Brushes.Red;
                if (d > 36) return new SolidColorBrush(Color.FromRgb(200, 140, 0));
            }
            return new SolidColorBrush(Color.FromRgb(0, 160, 0));
        }
        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
            => throw new NotImplementedException();
    }

    /// <summary>Boolean → Visibility.</summary>
    public class BoolToVisibilityConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
            => value is true ? Visibility.Visible : Visibility.Collapsed;
        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
            => throw new NotImplementedException();
    }

    /// <summary>Health state text → colour.</summary>
    public class HealthStateToColorConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            return value?.ToString() switch
            {
                "Normal" => new SolidColorBrush(Color.FromRgb(0, 160, 0)),
                "Elevated" or "Degraded" => new SolidColorBrush(Color.FromRgb(200, 140, 0)),
                "WARNING" => Brushes.Red,
                _ => Brushes.Gray
            };
        }
        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
            => throw new NotImplementedException();
    }

    /// <summary>Plant status text (NORMAL/DEGRADED/ABNORMAL) → background colour for the status card.</summary>
    public class PlantStatusToBackgroundConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            return value?.ToString() switch
            {
                "NORMAL" => new SolidColorBrush(Color.FromRgb(200, 240, 200)),
                "DEGRADED" => new SolidColorBrush(Color.FromRgb(255, 200, 200)),
                "ABNORMAL" => new SolidColorBrush(Color.FromRgb(255, 140, 140)),
                _ => Brushes.White
            };
        }
        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
            => throw new NotImplementedException();
    }

    /// <summary>Plant status text → foreground colour.</summary>
    public class PlantStatusToForegroundConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            return value?.ToString() switch
            {
                "NORMAL" => new SolidColorBrush(Color.FromRgb(0, 120, 0)),
                "DEGRADED" => new SolidColorBrush(Color.FromRgb(180, 0, 0)),
                "ABNORMAL" => new SolidColorBrush(Color.FromRgb(220, 0, 0)),
                _ => Brushes.Black
            };
        }
        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
            => throw new NotImplementedException();
    }

    /// <summary>Plant status text → border colour (thick border highlight).</summary>
    public class PlantStatusToBorderConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            return value?.ToString() switch
            {
                "NORMAL" => new SolidColorBrush(Color.FromRgb(0, 160, 0)),
                "DEGRADED" => new SolidColorBrush(Color.FromRgb(200, 40, 40)),
                "ABNORMAL" => new SolidColorBrush(Color.FromRgb(220, 0, 0)),
                _ => Brushes.Gray
            };
        }
        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
            => throw new NotImplementedException();
    }

    /// <summary>Active alarm count → foreground colour for status bar.</summary>
    public class AlarmCountToColorConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            if (value is int count)
            {
                if (count == 0) return new SolidColorBrush(Color.FromRgb(0, 120, 0));
                if (count <= 2) return new SolidColorBrush(Color.FromRgb(200, 140, 0));
                return Brushes.Red;
            }
            return Brushes.Black;
        }
        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture)
            => throw new NotImplementedException();
    }
}
