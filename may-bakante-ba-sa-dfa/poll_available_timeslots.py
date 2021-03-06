import json
import cfscrape
import datetime
import time
import argparse
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from constants import SITES_JSON
from db_factory import DBFactory


AVAILABLE_TIMESLOT_URI = 'https://www.passport.gov.ph/appointment/timeslot/available'

SCHEDULE_XHR_HEADERS = {
    'X-Requested-With': 'XMLHttpRequest',
    'Origin': 'https://www.passport.gov.ph',
    'Referer': 'https://www.passport.gov.ph/appointment/individual/schedule'
}

class PollAvailableTimeslots(object):
    def __init__(self):
        self._scraper = cfscrape.create_scraper()


    def execute(self, save_db_mode):
        try:
            sites = self._load_sites()
            current_date, year_after_date = self._get_from_to_dates()
            poll_start_time = int(round(time.time() * 1000))

            if save_db_mode:
                process_data = self._aggregate_data
                self._db = DBFactory.create()
                self._last_availability = self._get_last_availability_per_site()
            else:
                process_data = self._print_data
                self._timeslot_availability = []

            self._timeslot_availability = []

            for site in sites:
                available_timeslots = self._get_timeslots_availability(current_date, year_after_date, site['siteId'])
                process_data(site['name'], available_timeslots, poll_start_time)

            if save_db_mode and self._timeslot_availability:
                self._save_timeslot_availability()

        except Exception as ex:
            print("{}: {}".format(type(ex).__name__, ex))


    def _save_timeslot_availability(self):
        res = self._db.timeslot_availability.insert_many(self._timeslot_availability)
        n_inserted = len(res.inserted_ids)

        if n_inserted:
            print("Successfully inserted new timeslot_availability for {} sites".format(n_inserted))


    def _aggregate_data(self, site, available_timeslots, poll_start_time):
        if self._is_available_timeslots_changed(site, available_timeslots):
            self._timeslot_availability.append({
                'site': site,
                'availableTimeslots': available_timeslots,
                'pollStartTime': poll_start_time
            })


    def _print_data(self, site, available_timeslots, poll_start_time):
        print()
        print(site)
        print(' > Available ({})'.format(len(available_timeslots)))

        if len(available_timeslots):
            print('    {}'.format('\n    '.join([ self._millis_to_date(a) for a in available_timeslots])))


    def _get_last_availability_per_site(self):
        pipeline = [
            {
                '$sort': { 'pollStartTime': 1 }
            },
            {
                '$group' : {
                    '_id': '$site',
                    'id': { '$last': '$_id' },
                    'availableTimeslots': { '$last': '$availableTimeslots' }
                }
            }
        ]
        last_availability = self._db.timeslot_availability.aggregate(pipeline)
        return { a['_id']: a['availableTimeslots'] for a in last_availability }


    def _is_available_timeslots_changed(self, site, new_available_timeslots):
        return not self._last_availability or \
                (site in self._last_availability and new_available_timeslots != self._last_availability[site])


    def _load_sites(self):
        with open(SITES_JSON) as datafile:
            return json.load(datafile)


    def _get_timeslots_availability(self, from_date, to_date, site_id):
        timeslots = self._scraper.post(AVAILABLE_TIMESLOT_URI, \
                data={'fromDate': from_date, 'toDate': to_date, 'siteId': site_id, 'requestedSlots': 1}, \
                headers=SCHEDULE_XHR_HEADERS, verify=False).json()

        return [ t['AppointmentDate'] for t in timeslots if t['IsAvailable'] ]


    def _get_from_to_dates(self):
        today = datetime.date.today()
        return today.strftime('%Y-%m-%d'), \
                (today + datetime.timedelta(days=365)).strftime('%Y-%m-%d')


    def _millis_to_date(self, millis):
        try:
            return datetime.datetime.fromtimestamp(millis / 1000.0) \
                                    .strftime('%a, %b %d %Y %I:%M %p')
        except TypeError:
            return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser( \
        description="Poll available timeslots from DFA's Passport Appointment System")
    parser.add_argument('-s', '--save-db', action='store_true', \
        help="Save available timeslots to a database instead of printing in console")
    args = parser.parse_args()

    poll_timeslots = PollAvailableTimeslots()
    poll_timeslots.execute(args.save_db)
