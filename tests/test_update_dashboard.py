import unittest
from datetime import date

import update_dashboard as dashboard


class ParserTests(unittest.TestCase):
    def test_schedule_excludes_morning_and_uses_room_registration_link(self):
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
        self.assertEqual(days['Monday'], [])
        self.assertIn('courseId=yoga', days['Tuesday'][0]['url'])

    def test_alert_lines_follow_facility_headings(self):
        page = """
        <div class="wysiwyg-content"><h3><strong>Facility Alert: Special schedules</strong></h3>
        <p><strong><u>Recreation Centers:</u></strong><br>Thursday, September 10, 2026 | CLOSED<br>
        <strong><u>Pools:</u></strong><br><strong><u>Boyden Pool</u></strong><br>Thursday, September 10, 2026 | 11am - 1pm<br>
        <strong><u>RockWell:</u></strong><br>Thursday, September 10, 2026 | 12pm - 8pm<br>
        <strong><u>Group Fitness:</u></strong><br>Thursday, September 10, 2026 | CANCELED</p></div>
        <h2>Hours and Schedules</h2><p>View Hours of Operation for all Facilities</p>
        """
        alerts = dashboard.classify_alerts(page,date(2026,9,9))
        self.assertEqual(alerts['gym'][0]['text'],'Thursday, September 10, 2026 | CLOSED')
        self.assertEqual(alerts['pools'][0]['facility'],'Boyden Pool')
        self.assertNotIn('View Hours',str(alerts))

    def test_availability_is_scoped_to_requested_date(self):
        body = ('Wednesday, September 9, 2026 6:30 PM 0 spots available '
                'Thursday, September 10, 2026 6:30 PM 7 spots remaining')
        self.assertEqual(dashboard.spot_text(body, '6:30pm', date(2026, 9, 10)),
                         '7 spots available')

    def test_registration_endpoint_cards_are_parsed(self):
        page='''<div class="card" data-instance-dates="Thursday, September 10, 2026"
          data-instance-times="4:30 PM - 5:30 PM"><div class="spots-tag">7 spots available</div></div>'''
        found=dashboard.parse_availability_html(page)
        self.assertEqual(found[('2026-09-10',dashboard.ptime('4:30pm'))],'7 spots available')


if __name__ == '__main__':
    unittest.main()
