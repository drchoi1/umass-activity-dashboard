import unittest
from datetime import date, datetime, timedelta

import update_dashboard as dashboard


class ParserTests(unittest.TestCase):
    def test_schedule_excludes_morning_and_uses_room_registration_link(self):
        page = """
        <h2>Morning | Class Start Times: 7:00am - 11:45am</h2>
        <section class="day"><h3>Monday</h3><article class="event">
        <div class="event-title">Pilates 60</div><div class="event-time">7:30am - 8:30am</div>
        <a class="event-studio" href="https://recwell.umass.edu/Program/GetProgramDetails?courseId=pilates">Room 215</a></article></section>
        <h2>Afternoon | Class Start Times: 12:00pm - 4:45pm</h2>
        <section class="day"><h3>Tuesday</h3><article class="event">
        <div class="event-title">Vinyasa Yoga 60</div><div class="event-time">4:30pm - 5:30pm</div>
        <a class="event-studio" href="/program/GetProgramDetails?courseId=yoga">Room 210</a></article></section>
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

    def test_after_8pm_opens_tomorrow_and_keeps_today_available(self):
        dates=[date(2026,9,7+i) for i in range(7)]
        self.assertEqual(dashboard.initial_day_index(dates,datetime(2026,9,9,20,0)),3)
        self.assertEqual(dates[2],date(2026,9,9))

    def test_dashboard_covers_current_and_following_week(self):
        dates=dashboard.week_dates()
        self.assertEqual(len(dates),14)
        self.assertEqual(dates[-1]-dates[0],timedelta(days=13))

    def test_skating_events_use_finnly_dates_across_both_weeks(self):
        dates=[date(2026,9,14)+timedelta(days=i) for i in range(14)]
        events=[
            {'EventTypeName':'Public Skating','EventStartTime':'2026-09-15T11:10:00','EventEndTime':'2026-09-15T12:30:00','Closed':False},
            {'EventTypeName':'Public Skating','EventStartTime':'2026-09-22T16:00:00','EventEndTime':'2026-09-22T16:50:00','Closed':False},
            {'EventTypeName':'Public Skating','EventStartTime':'2026-09-15T09:00:00','EventEndTime':'2026-09-15T10:00:00','Closed':True},
            {'EventTypeName':'Private Rental','EventStartTime':'2026-09-15T13:00:00','EventEndTime':'2026-09-15T14:00:00','Closed':False},
        ]
        result=dashboard.parse_skating_events(events,dates)
        self.assertEqual(result['2026-09-15'],['11:10 AM–12:30 PM'])
        self.assertEqual(result['2026-09-22'],['4:00 PM–4:50 PM'])
        self.assertEqual(result['2026-09-16'],[])


if __name__ == '__main__':
    unittest.main()
