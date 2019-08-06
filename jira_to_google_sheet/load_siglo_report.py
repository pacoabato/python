# loads data from Jira (via REST API) to Google Sheet report
# uses Python3
# python libraries required: gspread oauth2client xlrd

# author: Paco Abato - pacoabato@gmail.com
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

# To work with google sheets
import gspread
# To authenticate in google sheets
from oauth2client.service_account import ServiceAccountCredentials

from datetime import datetime
import json
import requests
import base64
from string import Template


SCRIPT_VERSION = 'v3.11 - 20190629'


# Location of config and credentials files
BASE_DIR = '/media/report_files/'

# Google's credentials file
CLIENT_SECRET_FILE = 'client_secret.json'

JIRA_CREDENTIALS_FILE = 'jira_credentials.json'

CONFIG_FILE = 'config.json'
# The team key is used to determine if all the people that worked in an issue were from the team

URL_FILTER_ISSUES = Template('https://domain.com/jira/rest/api/2/filter/$filter_id')
URL_WORKLOG_TEMPLATE = Template('https://domain.com/jira/rest/api/2/issue/$issue_id/worklog/')
URL_ONE_ISSUE = Template('https://domain.com/jira/rest/api/2/issue/$issue_id/')

GOOGLE_SHEET_NAME = "Google Sheet's Name"

# tabs in google sheet
TAB_JIRADATA = 'JIRADATA'
TAB_TASKSDATA = 'TASKSDATA'
TAB_ERRORES = 'Errores'

NUM_ROWS_TO_INSERT = 5000

# if the assigned person's spentTime in the issue represents lower percentage than
# this value the issue is considered as shared
conf_percentage_shared_issue = 0.95

# the ID of the filter in Jira that provides the tasks to be analyzed
conf_filter_id = 123456
conf_team = []

# In https://console.developers.google.com/ Google Sheets API and Google Drive API must be both of them enabled

# This is the scope to use:
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

creds = ServiceAccountCredentials.from_json_keyfile_name(BASE_DIR + CLIENT_SECRET_FILE, scope)
client = gspread.authorize(creds)
google_sheet = client.open(GOOGLE_SHEET_NAME)

def run_main():
	print('Checking script version validity...')
	script_ver = google_sheet.worksheet('Índice').acell('C22').value
	if script_ver != SCRIPT_VERSION:
		print('Script version', SCRIPT_VERSION, 'not valid. It should be:', script_ver)
		return

	print('Loading report info...')
	creds = read_credentials()

	if not check_credentials(creds):
		print('You must include your credentials into file ' + JIRA_CREDENTIALS_FILE)
	
	load_config()

	auth = get_auth_code(creds['user_name'], creds['password'])
	issues = find_issues(auth)
	
	if len(issues) == 0:
		return

	dict_issues_key_summary = {}
	jiradata = []
	tasks_data = []
	dict_issue_fix_version = {}

	# issues with different fix version than its parents
	errors_different_version = []
	errors_different_version.append(['** Tareas con distinta versión que su tarea padre.'])
	errors_different_version.append(['Tarea', 'Padre', 'Descripción Tarea', 'Descripción Padre', 'Asignada a', 'Enlace Tarea'])

	# open issues with no remaining time
	errors_open_no_remaining = []
	errors_open_no_remaining.append(['** Tareas abiertas sin remaining (ETC).'])
	errors_open_no_remaining.append(['Tarea', 'Descripción', 'Asignada a', 'Enlace'])

	# open issues with last upadte more than one month ago
	errors_open_old_updated = []
	errors_open_old_updated.append(['** Tareas abiertas actualizadas por última vez hace más de un mes.'])
	errors_open_old_updated.append(['Tarea', 'Descripción', 'Asignada a', 'Última actualización', 'Enlace'])

	# closed issues with remaining time
	errors_closed_with_remaining = []
	errors_closed_with_remaining.append(['** Tareas cerradas con remaining (ETC).'])
	errors_closed_with_remaining.append(['Tarea', 'Descripción', 'Asignada a', 'Enlace'])

	# closed issues with zero spent time
	errors_closed_with_zero_spent = []
	errors_closed_with_zero_spent.append(['** Tareas cerradas con tiempo imputado cero.'])
	errors_closed_with_zero_spent.append(['Tarea', 'Descripción', 'Asignada a', 'Enlace'])

	# issues deviated
	errors_issues_deviated = []
	errors_issues_deviated.append(['** Tareas desviadas (Estimado < Imputado + ETC).'])
	errors_issues_deviated.append(['Tarea', 'Descripción', 'Asignada a', 'Enlace'])

	# "cambios de alcance" with no original estimate
	errors_np_no_estimate = []
	errors_np_no_estimate.append(['** Cambios de alcance sin estimación original.'])
	errors_np_no_estimate.append(['Tarea', 'Descripción', 'Asignada a', 'Enlace'])

	# parent issues with spent time
	errors_parent_with_spent = []
	errors_parent_with_spent.append(['** Tareas padre con tiempo imputado.'])
	errors_parent_with_spent.append(['Tarea', 'Descripción', 'Asignada a', 'Enlace'])

	print('Analyzing downloaded info...')

	for issue in issues:
		dict_issue_fix_version[issue['id']] = issue['fields']['fixVersions'][0]['name']

	analyzed_issues = 1

	for issue in issues:
		if analyzed_issues % 100 == 0:
			print(analyzed_issues, 'issues analyzed.')
		analyzed_issues += 1
		issue_id = issue['id']
		issue_key = issue['key']
		fields = issue['fields']
		issue_link = 'https://domain.com/jira/browse/' + issue_key # TODO put this URL in a Template constant
		issue_summary = fields['summary']
		dict_issues_key_summary[issue_key] = issue_summary
		issue_fix_version = fields['fixVersions'][0]['name']
		
		issue_assigned_to = 'Sin asignar'
		issue_field_assigned_to = fields['assignee']
		if issue_field_assigned_to:
			issue_assigned_to = issue_field_assigned_to['displayName']
		
		issue_status = fields['status']['name']
		issue_created = format_long_date_string(fields['created'], False)
		issue_updated = format_long_date_string(fields['updated'], False)
		issue_resolved = format_long_date_string(fields['resolutiondate'], False)
		issue_resolved_month = format_long_date_string(fields['resolutiondate'], True)
		issue_incidence_type = ''
		issue_field_incidence_type = fields['customfield_15190']
		if issue_field_incidence_type:
			issue_incidence_type = issue_field_incidence_type['value']
		issue_id = issue['id']
		worklogs = find_worklogs(auth, issue_id)

		is_shared = calculate_shared_issue(worklogs, issue_assigned_to)
		is_team_exclusive = calculate_team_exclusive(worklogs)
		project_name = fields['project']['name']
		issue_type = fields['issuetype']['name']
		issue_title = issue_summary
		issue_time_original_estimate = to_hours(fields['timeoriginalestimate'])
		issue_time_estimate = to_hours(fields['timeestimate'])
		issue_time_spent = to_hours(fields['timespent'])
		jiradata_base = [project_name, issue_type, 
			issue_key, issue_title, issue_time_original_estimate,
			issue_time_estimate, issue_time_spent]

		if len(jiradata) > NUM_ROWS_TO_INSERT:
			print('Expected maximum number of records (', NUM_ROWS_TO_INSERT, ') exceeded.')
			print('You should update the dynamic tables indexes in Google Sheet and the constant NUM_ROWS_TO_INSERT in the script.')
			# TODO should abort loading data?

		issue_parent_summary = ''
		issue_parent_key = ''
		parent_fix_version = ''
		if 'parent' in fields:
			issue_field_parent = fields['parent']
			issue_parent_summary = issue_field_parent['fields']['summary']
			issue_parent_key = issue_field_parent['key']
			if issue_field_parent['id'] in dict_issue_fix_version:
				parent_fix_version = dict_issue_fix_version[issue_field_parent['id']]
		if parent_fix_version and issue_fix_version and parent_fix_version != issue_fix_version:
			errors_different_version.append([issue_key, issue_parent_key, issue_summary, issue_parent_summary, issue_assigned_to, issue_link])
		
		if issue_parent_key:
			# if issue it's not a parent issue

			if issue_status in ['Open', 'In progress', 'Reopened', 'Paused', 'Blocked']:
				if issue_time_estimate <= 0:
					errors_open_no_remaining.append([issue_key, issue_summary, issue_assigned_to, issue_link])

				delta = datetime.today() - datetime.strptime(issue_updated, '%d/%m/%Y')
				if delta.days > 30:
					errors_open_old_updated.append([issue_key, issue_summary, issue_assigned_to, issue_updated, issue_link])
			
			if issue_status in ['Resolved', 'Closed']: # doesn't take into account 'Rejected' wich can have any condition and it doesn't matter
				if issue_time_estimate > 0:
					errors_closed_with_remaining.append([issue_key, issue_summary, issue_assigned_to, issue_link])
				
				if issue_time_spent == 0:
					errors_closed_with_zero_spent.append([issue_key, issue_summary, issue_assigned_to, issue_link])
			
			if int(issue_time_original_estimate) < int(issue_time_spent) + int(issue_time_estimate):
				errors_issues_deviated.append([issue_key, issue_summary, issue_assigned_to, issue_link])
			
		else:
			# if it is a parent issue
			issue_aggregate_time_original_estimate = fields['aggregatetimeoriginalestimate']
			issue_aggregate_time_estimate = fields['aggregatetimeestimate']
			issue_aggregate_time_spent = fields['aggregatetimespent']
			if issue_aggregate_time_original_estimate and issue_aggregate_time_estimate and issue_aggregate_time_spent \
				and int(issue_aggregate_time_original_estimate) < int(issue_aggregate_time_spent) + int(issue_aggregate_time_estimate):
				errors_issues_deviated.append([issue_key, issue_summary, issue_assigned_to, issue_link])
			
			if issue_time_spent > 0:
				errors_parent_with_spent.append([issue_key, issue_summary, issue_assigned_to, issue_link])

		if issue_summary.strip().startswith('NP_') or issue_summary.strip().startswith('NP-'):
			if not issue_time_original_estimate or issue_time_original_estimate == 0:
				errors_np_no_estimate.append([issue_key, issue_summary, issue_assigned_to, issue_link])


		jiradata.extend(
			get_jiradata_records(
				jiradata_base,
				worklogs,
				is_shared,
				is_team_exclusive))

		task_record = [issue_key, issue_summary, issue_assigned_to,
			issue_time_original_estimate, issue_time_estimate, issue_time_spent,
			issue_fix_version, issue_status, issue_created, issue_updated, 
			issue_resolved, issue_resolved_month, issue_incidence_type,
			issue_parent_summary, issue_link, is_shared, is_team_exclusive]

		tasks_data.append(task_record)

	# end for issue in issues

	len_tasks_data = len(tasks_data)
	print('Tasks:', len_tasks_data)
		
	updateTabData(TAB_JIRADATA, jiradata)
	updateTabData(TAB_TASKSDATA, tasks_data)

	errors = []
	add_errors_if_exist(errors, errors_different_version)
	add_errors_if_exist(errors, errors_open_no_remaining)
	add_errors_if_exist(errors, errors_open_old_updated)
	add_errors_if_exist(errors, errors_closed_with_remaining)
	add_errors_if_exist(errors, errors_closed_with_zero_spent)
	add_errors_if_exist(errors, errors_issues_deviated)
	add_errors_if_exist(errors, errors_np_no_estimate)
	add_errors_if_exist(errors, errors_parent_with_spent)

	updateTabData(TAB_ERRORES, errors)

	# Register the date and person updating the report (in the Indice tab of the report)
	google_sheet.worksheet('Índice').update_acell('E4', datetime.today().strftime('%d/%b/%Y') + ' (' + creds['user_name'] + ')')

	print('Finished.')

def add_errors_if_exist(errors_general, errors_subtype):
	if len(errors_subtype) > 2:
		# if there are no errors, the list contains anyway two elements (title and headers)
		errors_general.extend(errors_subtype)

def to_hours(seconds):
	''' Accepts a number of seconds and returns the
	equivalent quantity in hours (zero if param is None).'''
	if seconds:
		return int(seconds) / 3600
	else:
		return 0

def updateTabData(tab, data):
	''' Clears the tab's content except the header row and then adds the data.
	tab is the name of a tab and data is a list of rows to be inserted into that tab'''
	clearTabContent(google_sheet, tab)
	fill_with_blanks(data, NUM_ROWS_TO_INSERT)

	data = data or ['']

	google_sheet.values_update(
		tab + '!A2', # skip headers row
		params={'valueInputOption': 'USER_ENTERED'},
		# USER_ENTERED so it respects the type of data (RAW would convert to string appending an apostrophe like '234)
		body={'values': data}
	)

	print(tab, 'updated.')


def fill_with_blanks(a_list, num_rows):
	''' Fills the list withs arrays of empty strings up to num_rows elements (at the
	end a_list's size will be num_rows. Each appended array will contain num_cols 
	empty strings.'''

	empty_list = ['']
	s = len(a_list)
	for i in range(s, num_rows):
		a_list.append(empty_list)


def clearTabContent(google_sheet, tab):
	google_worksheet = google_sheet.worksheet(tab)
	google_worksheet.resize(rows=2) 
	# leaves the header and the first data row 
	# (so header's style is not propagated to new 
	# rows when they are added)


def get_jiradata_records(jiradata_base, worklogs, is_shared, is_team_exclusive):
	''' Builds records for JIRADATA tab using the info from
	jiradata_base and adding a new record for each worklog
	with proper worklog's info.
	jiradata_base is a list containing info from the issue.
	worklogs is a list of JSON objects with fields:
	started, author, timeSpent and comment (as returned 
	by find_worklogs method).'''

	jiradata_records = []
	for worklog in worklogs:
		jiradata_record = []
		jiradata_record.extend(jiradata_base)
		jiradata_record.append(worklog['started'])
		jiradata_record.append(worklog['author'])
		jiradata_record.append(worklog['timeSpent'])
		jiradata_record.append(worklog['comment'])
		jiradata_record.append(is_shared)
		jiradata_record.append(is_team_exclusive)

		jiradata_records.append(jiradata_record)

	return jiradata_records


def calculate_shared_issue(worklog, issue_assigned_to):
	''' Takes a list of JSON objects with attributes (author, timeSpent and comment)
	for worklogs of an issue and the person to whom the issue is assigned.
	Returns if the issue (for which the worklog is related to) contains spent times
	from several people.'''
	
	# don't count as shared if the most timespent if from the assigned person
	acum_total = 0
	acum_author = 0
	for json in worklog:
		author = json['author']
		timeSpent = json['timeSpent']
		acum_total += timeSpent
		if author == issue_assigned_to:
			acum_author += timeSpent
	is_shared = (acum_total > 0) and (acum_author / acum_total < conf_percentage_shared_issue)
	
	return 'Sí' if is_shared else 'No'

def calculate_team_exclusive(worklog):
	'''Returns true if all the people that worked in the issue were in the 
	team pointed in the config file.'''

	for json in worklog:
		if json['author_username'] not in conf_team:
			return 'No'
	
	return 'Sí'

def print_connection_error(response):
	print('')
	print('********************************************************************')
	print('Response error: ', response.status_code)
	print('Maybe the Jira filter (id filter= ' + str(conf_filter_id) + ')is broken or misconfigured,')
	print('the credentials are wrong or the user has no access to the filter.')
	print('********************************************************************')
	print('')

def find_issues(auth_code):
	headers = get_basic_auth_header(auth_code)

	url_find_issues = None
	response = requests.get(URL_FILTER_ISSUES.substitute(filter_id=conf_filter_id), headers=headers)
	if not response.ok:
		print_connection_error(response)		
		return []
		
	response_json = response.json()
	if len(response_json) > 0:
		url_find_issues = response_json['searchUrl']
	
	if not url_find_issues:
		print('Could not obtain Jira filter\'s URL from: ', URL_FILTER_ISSUES.substitute(filter_id=conf_filter_id))
		return []

	issues = []

	max_res = 100 # max results per page
	init_pos = 0
	total_num_issues = 1 # to allow at least one request

	while init_pos < total_num_issues:
		pagination = build_pagination_str(init_pos, max_res)
		response = requests.get(url_find_issues + pagination, headers=headers)
		if not response.ok:
			print_connection_error(response)
			return []
		response_json = response.json()
		if len(response_json) > 0:
			total_num_issues = int(response_json['total'])
			issues.extend(response_json['issues'])
		else:
			total_num_issues = 0
		
		init_pos += max_res
		print('Downloading issues in progress:', init_pos, 'of', total_num_issues, 'issues.')
	
	num_issues_downloaded = len(issues)
	
	if num_issues_downloaded != total_num_issues:
		print('Number of issues in Jira: ', total_num_issues)
		print('Number of issues downloaded from Jira: ', num_issues_downloaded)
		raise BaseException('Not all issues where downloaded from Jira')

	print('Number of downloaded issues from Jira: ', num_issues_downloaded)
	return issues

def get_basic_auth_header(auth_code):
	return {
		'Content-type': 'application/json',
		'Authorization': 'Basic ' + auth_code}

def find_worklogs(auth_code, param_issue_id):
	''' Returns a list of JSON objects with attributes (author, timeSpent and comment)
	for each registered worklog in the issue denoted by param_issue_id'''

	headers = get_basic_auth_header(auth_code)
	response = requests.get(
		URL_WORKLOG_TEMPLATE.substitute(issue_id=param_issue_id),
		headers=headers)
	
	if not response.ok:
		print ('Response error: ', response.status_code)
		return
	
	response_json = response.json()

	worklogs = []
	for worklog in response_json['worklogs']:
		json = {}
		json['author'] = worklog['author']['displayName'] # full name
		json['author_username'] = worklog['author']['name'] # Jira user
		json['timeSpent'] = int(worklog['timeSpentSeconds']) / 3600
		json['comment'] = worklog['comment']
		json['started'] = format_long_date_string(worklog['started'], False)
		worklogs.append(json)

	return worklogs


def format_long_date_string(str_date, onlyYearMonth):
	''' node: a date-string in format '2019-04-01T19:59:00.000+0200'
	returns: a date string with format '01/04/2019' if onlyYearMonth is
	False, otherwise '2019/04' will be returned.'''

	if str_date is None or len(str_date) == 0:
		d = ''
	else:
		resultDateMask = '%Y/%m' if onlyYearMonth else '%d/%m/%Y'
		d = datetime.strptime(str_date, '%Y-%m-%dT%H:%M:%S.%f%z').strftime(resultDateMask)
		
	return d


def get_auth_code(user, password):
	''' Returns a string for Basic Authentication in Jira from 
	provided user and password.'''

	auth_code = user + ':' + password
	auth_code = base64.b64encode(bytes(auth_code, 'utf-8'))
	auth_code = auth_code.decode('ascii')
	return auth_code


def load_config():
	''' Reads configuration info from file.'''

	global conf_percentage_shared_issue
	global conf_filter_id
	global conf_team
	conf = {}
	with open(BASE_DIR + CONFIG_FILE) as f:
		conf = json.load(f)
	
	if 'sharedPercentage' in conf:
		conf_percentage_shared_issue = conf['sharedPercentage']
	if 'filterId' in conf:
		conf_filter_id = conf['filterId']
	if 'team' in conf:
		conf_team = conf['team']


def read_credentials():
	''' Reads the Jira access credentials from file and returns the data
	in a JSON object.'''

	creds = {}
	with open(BASE_DIR + JIRA_CREDENTIALS_FILE) as f:
		creds = json.load(f)
	
	return creds


def check_credentials(creds):
	''' Returns whether the credentials are ok.'''

	return (creds is not None and
		'user_name' in creds and
		'password' in creds and
		creds['user_name'] is not None and
		len(creds['user_name']) > 0 and
		creds['password'] is not None and
		len(creds['password']) > 0)


def build_pagination_str(init_pos, max_res):
	''' Returns a string with the parameters to implement pagination
	in Jira REST queries.'''
	
	return '&startAt=' + str(init_pos) + '&maxResults=' + str(max_res)

# Runs the "main" method if this .py file is executed directly:
if __name__ == "__main__":
	run_main()
	


