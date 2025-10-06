import os
import django
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date
import subprocess
import logging

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'multigam.settings')
django.setup()

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Set up cron job for GAM reports fetching - fetches all accounts every 30 minutes for today date'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force setup even if cron job already exists'
        )
        parser.add_argument(
            '--test',
            action='store_true',
            help='Test the cron job setup without actually installing it'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Setting up GAM Reports Cron Job...')
        )
        
        force = options.get('force', False)
        test_mode = options.get('test', False)
        
        # Check if cron job already exists
        if not force and not test_mode:
            existing_cron = self._check_existing_cron()
            if existing_cron:
                self.stdout.write(
                    self.style.WARNING(
                        f'⚠️ Cron job already exists:\n{existing_cron}\n'
                        'Use --force to overwrite or --test to test setup'
                    )
                )
                return
        
        # Create the cron script
        cron_script_path = '/home/ubuntu/gam-reports-cron.sh'
        cron_script_content = self._create_cron_script()
        
        if test_mode:
            self.stdout.write('🧪 TEST MODE - Would create the following:')
            self.stdout.write(f'Script: {cron_script_path}')
            self.stdout.write(f'Content:\n{cron_script_content}')
            self.stdout.write('Crontab entry: */30 * * * * /home/ubuntu/gam-reports-cron.sh')
            return
        
        try:
            # Create the cron script file
            self._create_cron_script_file(cron_script_path, cron_script_content)
            
            # Set up the cron job
            self._setup_crontab()
            
            # Verify the setup
            self._verify_setup()
            
            self.stdout.write(
                self.style.SUCCESS(
                    '✅ Cron job setup completed successfully!\n'
                    '📅 Schedule: Every 30 minutes\n'
                    '🎯 Target: All eligible accounts for today date\n'
                    '📊 Parallel processing: 100 workers, batch size 93\n'
                    '💰 Currency: Forced USD\n'
                    '🔍 Unknown metrics: Desktop data processed as unknown'
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Cron job setup failed: {str(e)}')
            )
            raise
    
    def _create_cron_script(self):
        """Create the cron script content"""
        return '''#!/bin/bash
# GAM Reports Cron Job - Fetches all accounts every 30 minutes for today date
# Created: ''' + str(timezone.now()) + '''

# Set up logging
LOG_DIR="/var/log/gam-reports"
sudo mkdir -p "$LOG_DIR"
sudo chown ubuntu:ubuntu "$LOG_DIR"

LOG_FILE="$LOG_DIR/gam-reports-$(date +%Y%m%d).log"
LOCK_FILE="/tmp/gam_reports_cron.lock"

# Check if another instance is running
if [ -f "$LOCK_FILE" ]; then
    echo "$(date): Another cron job instance is running. Skipping." >> "$LOG_FILE"
    exit 0
fi

# Create lock file
echo $$ > "$LOCK_FILE"

# Function to cleanup on exit
cleanup() {
    rm -f "$LOCK_FILE"
}
trap cleanup EXIT

# Log start
echo "$(date): === Starting GAM Reports Cron Job ===" >> "$LOG_FILE"
echo "$(date): Project directory: /home/ubuntu/Backend" >> "$LOG_FILE"
echo "$(date): Virtual environment: /home/ubuntu/Backend/venv" >> "$LOG_FILE"

# Change to project directory
cd /home/ubuntu/Backend || {
    echo "$(date): Failed to change to project directory" >> "$LOG_FILE"
    exit 1
}
echo "$(date): Changed to project directory successfully" >> "$LOG_FILE"

# Activate virtual environment
source venv/bin/activate || {
    echo "$(date): Failed to activate virtual environment" >> "$LOG_FILE"
    exit 1
}
echo "$(date): Virtual environment activated successfully" >> "$LOG_FILE"

# Check Django configuration
echo "$(date): Checking Django configuration..." >> "$LOG_FILE"
python manage.py check --deploy >> "$LOG_FILE" 2>&1 || {
    echo "$(date): Django configuration check failed" >> "$LOG_FILE"
    exit 1
}
echo "$(date): Django system check passed" >> "$LOG_FILE"

# Test database connection
echo "$(date): Testing database connection..." >> "$LOG_FILE"
python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('Database connected')" >> "$LOG_FILE" 2>&1 || {
    echo "$(date): Database connection failed" >> "$LOG_FILE"
    exit 1
}
echo "$(date): Database connection verified" >> "$LOG_FILE"

# Fetch GAM reports for today with all accounts
echo "$(date): Fetching GAM reports for today..." >> "$LOG_FILE"
python manage.py fetch_gam_reports --parallel --max-workers 100 --batch-size 93 --date-from $(date +%Y-%m-%d) --date-to $(date +%Y-%m-%d) >> "$LOG_FILE" 2>&1

# Check if the command was successful
if [ $? -eq 0 ]; then
    echo "$(date): GAM reports cron job completed successfully" >> "$LOG_FILE"
else
    echo "$(date): GAM reports cron job failed" >> "$LOG_FILE"
    exit 1
fi

echo "$(date): === GAM Reports Cron Job Completed ===" >> "$LOG_FILE"
'''
    
    def _create_cron_script_file(self, script_path, content):
        """Create the cron script file"""
        try:
            with open(script_path, 'w') as f:
                f.write(content)
            
            # Make the script executable
            os.chmod(script_path, 0o755)
            
            self.stdout.write(f'✅ Created cron script: {script_path}')
            
        except Exception as e:
            raise Exception(f'Failed to create cron script: {str(e)}')
    
    def _setup_crontab(self):
        """Set up the crontab entry"""
        try:
            # Remove any existing GAM reports cron jobs
            subprocess.run(['crontab', '-l'], capture_output=True, text=True)
            existing_cron = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
            
            if existing_cron.returncode == 0:
                # Filter out existing GAM reports entries
                lines = existing_cron.stdout.split('\n')
                filtered_lines = [line for line in lines if 'gam-reports-cron.sh' not in line and line.strip()]
                
                # Add new cron job
                new_cron_entry = '*/30 * * * * /home/ubuntu/gam-reports-cron.sh'
                filtered_lines.append(new_cron_entry)
                
                # Write new crontab
                new_cron_content = '\n'.join(filtered_lines) + '\n'
                subprocess.run(['crontab', '-'], input=new_cron_content, text=True, check=True)
            else:
                # No existing crontab, create new one
                new_cron_entry = '*/30 * * * * /home/ubuntu/gam-reports-cron.sh\n'
                subprocess.run(['crontab', '-'], input=new_cron_entry, text=True, check=True)
            
            self.stdout.write('✅ Crontab entry added successfully')
            
        except subprocess.CalledProcessError as e:
            raise Exception(f'Failed to setup crontab: {str(e)}')
    
    def _check_existing_cron(self):
        """Check if cron job already exists"""
        try:
            result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'gam-reports-cron.sh' in line:
                        return line.strip()
            return None
        except Exception:
            return None
    
    def _verify_setup(self):
        """Verify the cron job setup"""
        try:
            # Check if script exists and is executable
            script_path = '/home/ubuntu/gam-reports-cron.sh'
            if not os.path.exists(script_path):
                raise Exception('Cron script file not found')
            
            if not os.access(script_path, os.X_OK):
                raise Exception('Cron script is not executable')
            
            # Check crontab entry
            result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
            if result.returncode == 0:
                if 'gam-reports-cron.sh' not in result.stdout:
                    raise Exception('Cron job not found in crontab')
            
            self.stdout.write('✅ Cron job setup verified successfully')
            
        except Exception as e:
            raise Exception(f'Verification failed: {str(e)}')