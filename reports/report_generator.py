# report_generator.py (create this in the main project directory)

import csv
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ReportGenerator:
    def __init__(self, db_manager, reports_dir):
        self.db_manager = db_manager
        self.reports_dir = reports_dir
        if not os.path.exists(self.reports_dir):
            os.makedirs(self.reports_dir)

    def generate_daily_report(self, date=None):
        if date is None:
            date = datetime.now().date()
        date_str = date.strftime('%Y-%m-%d')
        filename = os.path.join(self.reports_dir, f"daily_attendance_report_{date_str}.csv")

        records = self.db_manager.get_attendance_records(start_date=date_str, end_date=date_str)

        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Student ID', 'Name', 'Date', 'Time'])
            if records:
                for record in records:
                    writer.writerow(record)
            else:
                writer.writerow(['No attendance recorded for this date.'])

        logger.info(f"Daily report generated: {filename}")
        return filename

    # Add methods for weekly, monthly, student-wise reports
    def generate_student_report(self, student_id):
        filename = os.path.join(self.reports_dir, f"student_attendance_report_{student_id}.csv")

        records = self.db_manager.get_attendance_records(student_id=student_id)

        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Student ID', 'Name', 'Date', 'Time'])
            if records:
                for record in records:
                    writer.writerow(record)
            else:
                writer.writerow([f'No attendance records found for {student_id}.'])

        logger.info(f"Student report generated: {filename}")
        return filename

# Example usage within main.py:
# from report_generator import ReportGenerator
# report_gen = ReportGenerator(db_manager, Config.REPORTS_DIR)
# report_gen.generate_daily_report()