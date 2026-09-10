import unittest
from datetime import date

import update_dashboard as dashboard


class ParserTests(unittest.TestCase):
    def test_schedule_includes_morning_and_room_registration_link(self):
        page = """
        <h2>Morning | Class Start Times: 7:00am - 11:45am</h2>
        <h3>Monday</h3>
        <div><p>Pilates 60</p><p>Instructor</p><p>7:30am - 8:30am</p>
        <a href="https://recwell.umass.edu/Program/GetProgramDetails?courseId=pilates">Room 215</a></div>
        <h2>Afternoon | Class Start Times: 12:00pm - 4:45pm</h2>
        <h3>Tuesday</h3>
        <div><p>Vinyasa Yoga 60</p><p>Instructor</p><p>4:30pm - 5:30pm</p>
        <a href="/program/GetProgramDetails?courseId=yoga">Room 210</a></div>
        """
        days = dashboard.parse_schedule(page)
        self.assertEqual(days['Monday'][0]['start'], '7:30am')
        self.assertIn('courseId=pilates', days['Monday'][0]['url'])
        self.assertIn('courseId=yoga', days['Tuesday'][0]['url'])

    def test_alert_lines_follow_facility_headings(self):
        page = """
        <p>Facility Alert: Special schedules this weekend.</p>
        <p>Recreation Centers:</p><p>Saturday | CLOSED</p>
        <p>Pools:</p><p>Boyden Pool</p><p>Saturday | 11am - 1pm</p>
        <p>RockWell:</p><p>Saturday | 12pm - 8pm</p>
        <p>Group Fitness:</p><p>Sunday classes are canceled.</p>
        <p>RecWell Fall Semester Hours</p>
        """
        alerts = dashboard.classify_alerts(page)
        self.assertIn('Saturday | CLOSED', alerts['gym'])
        self.assertIn('Saturday | 11am - 1pm', alerts['pools'])
        self.assertIn('Saturday | 12pm - 8pm', alerts['rock'])
        self.assertIn('Sunday classes are canceled.', alerts['fitness'])

    def test_availability_is_scoped_to_requested_date(self):
        body = ('Wednesday, September 9, 2026 6:30 PM 0 spots available '
                'Thursday, September 10, 2026 6:30 PM 7 spots remaining')
        self.assertEqual(dashboard.spot_text(body, '6:30pm', date(2026, 9, 10)),
                         '7 spots available')


if __name__ == '__main__':
    unittest.main()
