import re
import json
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import subprocess
import os

COURSES_DIR = 'courses'

BASE = 'https://suis.sabanciuniv.edu/prod/'
LIST_URL = BASE + 'SU_DEGREE.p_list_degree?P_LEVEL=UG&P_LANG=EN&P_PRG_TYPE='

PROGRAM_FILES = {
    'BSBIO': 'BIO.json',
    'BSCS': 'CS.json',
    'BAECON': 'ECON.json',
    'BSEE': 'EE.json',
    'BSMS': 'IE.json',
    'BSMAT': 'MAT.json',
    'BSME': 'ME.json',
    'BSDSA': 'DSA.json',  # Adding Data Science and Analytics program
    'BAMAN': 'MAN.json',  # Management program
    'BAPSIR': 'PSIR.json',  # Political Science and International Relations
    'BAPSY': 'PSY.json',  # Psychology program
    'BAVACD': 'VACD.json',  # Visual Arts and Visual Communication Design
}

# Predefined faculty courses - these are specific courses, not based on course attributes
FACULTY_COURSES = {
    'FENS': [
        'CS201', 'CS204', 'DSA210', 'EE200', 'EE202', 'ENS201', 'ENS202', 'ENS203',
        'ENS204', 'ENS205', 'ENS206', 'ENS207', 'ENS208', 'ENS209', 'ENS210', 'ENS211',
        'ENS214', 'ENS216', 'MAT204', 'MATH201', 'MATH202', 'MATH203', 'MATH204',
        'NS201', 'NS207', 'NS213', 'NS214', 'NS216', 'NS218', 'PHYS211'
    ],
    'FASS': [
        'ANTH255', 'ANTH326', 'CULT368', 'GEN341', 'LIT212', 'LIT359', 'PHIL202',
        'PHIL321', 'VA315', 'ECON201', 'ECON202', 'ECON204', 'HART292', 'HART311',
        'HIST205', 'HIST349', 'PSY201', 'PSY310', 'PSY340', 'IR201', 'IR301',
        'IR391', 'IR394', 'POLS250', 'POLS301', 'SOC201', 'SOC301', 'HART213',
        'HART293', 'VA201', 'VA203', 'VA312'
    ],
    'SBS': [
        'ACC201', 'FIN301', 'MGMT402', 'MKTG301', 'OPIM302', 'ORG301', 'ORG302'
    ]
}

def get_faculty_for_course(major, code):
    """Get the faculty (FENS/FASS/SBS) for a course if it's a faculty course, otherwise return None"""
    course_code = f"{major}{code}"
    for faculty, courses in FACULTY_COURSES.items():
        if course_code in courses:
            return faculty
    return None

def is_faculty_course(major, code):
    """Check if a course is a faculty course based on predefined lists"""
    return get_faculty_for_course(major, code) is not None


def get_program_codes():
    resp = requests.get(LIST_URL)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'lxml')
    codes = {}
    for a in soup.select('a[href*="P_PROGRAM="]'):
        m = re.search(r'P_PROGRAM=([^&]+)', a['href'])
        if m:
            codes[m.group(1)] = a.get_text(strip=True)
    return codes


def get_latest_term(code):
    url = BASE + f'SU_DEGREE.p_select_term?P_PROGRAM={code}&P_LANG=EN&P_LEVEL=UG'
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'lxml')
    opt = soup.select_one('select[name=P_TERM] option')
    return opt['value'] if opt else None


def map_category(title):
    t = title.lower()
    if 'university' in t and 'courses' in t:
        return 'university'
    if 'required' in t and 'courses' in t:
        return 'required'
    if 'core' in t and 'elective' in t:
        return 'core'
    if 'area' in t and 'elective' in t:
        return 'area'
    if 'free' in t and 'elective' in t:
        return 'free'
    if t == 'total':
        return 'university'  # Easy fix for university course problem, they are miss detected as total
    return 'unknown'  # Default to if no match

def parse_table(table, category):
    rows = []
    trs = table.find_all('tr')
    if not trs:
        return rows
    header = len(trs[0].find_all('th')) > 0
    for tr in trs[1 if header else 0:]:
        tds = [td.get_text(strip=True) for td in tr.find_all('td')]
        if len(tds) >= 5 and tds[1]:
            code = tds[1].replace('\xa0', ' ')
            parts = code.split()
            major = parts[0]
            number = ''.join(parts[1:]) if len(parts) > 1 else ''

            # Check if this course has an asterisk marker (faculty course indicator)
            has_asterisk = False
            if len(tds) > 0:
                first_cell_html = str(tr.find_all('td')[0])
                has_asterisk = '<center>&nbsp;*&nbsp;</center>' in first_cell_html or '<center> * </center>' in first_cell_html

            # Check if this is a faculty course and get the faculty name
            faculty_course = get_faculty_for_course(major, number)
            if faculty_course is None:
                faculty_course = "No"

            # Determine the correct EL_Type
            el_type = category
            # If the course has an asterisk and is a faculty course, and we're in a required section,
            # it should maintain its core elective status instead of being marked as required
            if has_asterisk and faculty_course != "No" and category == "required":
                el_type = "core"
            elif has_asterisk and faculty_course != "No" and category == "area":
                el_type = "area"
            elif has_asterisk and faculty_course != "No" and category == "free":
                el_type = "free"
            rows.append({
                'Major': major,
                'Code': number,
                'Course_Name': tds[2],
                'ECTS': tds[3],
                'Engineering': 0,
                'Basic_Science': 0,
                'SU_credit': tds[4],
                'Faculty': tds[5] if len(tds) > 5 else '',
                'EL_Type': el_type,
                'Faculty_Course': faculty_course,
            })
    return rows


def crawl_list(url, category):
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'lxml')
    table = soup.find('table')
    return parse_table(table, category) if table else []


def crawl_program(code, term):
    url = (BASE + 'SU_DEGREE.p_degree_detail?P_PROGRAM={code}&P_LANG=EN&P_LEVEL=UG'
           '&P_TERM={term}&P_SUBMIT=Select').format(code=code, term=term)
    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'lxml')
    results = []
    seen_courses = set()  # Track seen courses to avoid duplicates

    # First, try to extract category information from the name attribute
    for a in soup.select('a[name]'):
        name_attr = a.get('name', '')
        # Skip non-category anchors with improved pattern matching
        if not (name_attr.endswith('_CEL') or name_attr.endswith('_REQ') or
                name_attr.endswith('_AEL') or name_attr.endswith('_FEL') or name_attr.endswith('_ARE') or name_attr.endswith('_FRE') or
                name_attr == 'UC_FENS' or name_attr == 'UC_FASS' or
                name_attr.startswith('main') or
                # Add more specific patterns for different program types
                '_COR' in name_attr or '_C1' in name_attr or '_C2' in name_attr or '_CE1' in name_attr or '_CE2' in name_attr or
                '_PHL' in name_attr or '_MEL' in name_attr):  # Sometimes 'main' is used for categories
            continue

        # Get the category title from the parent element's text or the next bold text
        category_title = ""
        if a.parent and a.parent.find('b'):
            category_title = a.parent.find('b').get_text(strip=True)
        elif a.find_next('b'):
            category_title = a.find_next('b').get_text(strip=True)

        # Determine the category type based on the name attribute or title
        el_type = None
        if name_attr.endswith('_CEL') or '_COR' in name_attr or '_CE1' in name_attr or '_C1' in name_attr:
            el_type = 'core'
        elif name_attr.endswith('_CE2') or name_attr.endswith('_PHL') or name_attr.endswith('_C2') or '_MEL' in name_attr:
            el_type = 'extra_attribute'
        elif name_attr.endswith('_REQ'):
            el_type = 'required'
        elif name_attr.endswith('_AEL') or name_attr.endswith('_ARE'):
            el_type = 'area'
        elif name_attr.endswith('_FEL') or name_attr.endswith('_FRE'):
            el_type = 'free'
        elif name_attr == 'UC_FENS' or name_attr == 'UC_FASS':
            el_type = 'university'
        else:
            # If we can't determine from the name attribute, use the title text
            el_type = map_category(category_title)

        # Improved table finding logic - try multiple approaches
        table = None

        # Method 1: Look for tables in the next few siblings after the anchor
        current_element = a
        for _ in range(10):  # Look through next 10 elements
            current_element = current_element.find_next()
            if not current_element:
                break

            if current_element.name == 'table':
                # Check if this table has course-like structure
                if current_element.find('th', string=lambda s: s and ('Course' in s or 'Name' in s or 'ECTS' in s or 'SU Credits' in s)):
                    table = current_element
                    break
                # Also check for tables with course data even without headers
                rows = current_element.find_all('tr')
                if len(rows) > 1:  # Must have more than just header
                    first_data_row = None
                    for row in rows[1:]:  # Skip potential header
                        tds = row.find_all('td')
                        if len(tds) >= 5 and tds[1] and tds[1].get_text(strip=True):
                            # Check if the second column looks like a course code
                            course_text = tds[1].get_text(strip=True).replace('\xa0', ' ')
                            if re.match(r'^[A-Z]+\s*\d+', course_text):
                                table = current_element
                                break
                    if table:
                        break

        # Method 2: If no table found yet, try looking in parent table structure and finding next sibling tables
        if not table:
            parent_table = a.find_parent('table')
            if parent_table:
                # Look for the next table after the parent table
                next_element = parent_table.find_next_sibling()
                while next_element:
                    if next_element.name == 'tr':
                        # Check if this tr contains a table
                        nested_table = next_element.find('table')
                        if nested_table and nested_table.find('th', string=lambda s: s and ('Course' in s or 'Name' in s)):
                            table = nested_table
                            break
                    elif next_element.name == 'table':
                        if next_element.find('th', string=lambda s: s and ('Course' in s or 'Name' in s)):
                            table = next_element
                            break
                    next_element = next_element.find_next_sibling()

        # Method 3: Alternative approach - look for tables within a reasonable distance
        if not table:
            # Find all tables after this anchor within a reasonable scope
            all_tables = []
            current = a
            for _ in range(20):  # Look through next 20 elements
                current = current.find_next('table')
                if not current:
                    break
                all_tables.append(current)

            # Find the first table that looks like a course table
            for candidate_table in all_tables:
                if candidate_table.find('th', string=lambda s: s and ('Course' in s or 'Name' in s or 'ECTS' in s)):
                    table = candidate_table
                    break

        # If we found a table, parse it
        if table:
            new_rows = parse_table(table, el_type)
            for row in new_rows:
                course_id = f"{row['Major']}{row['Code']}"
                if course_id not in seen_courses:
                    results.append(row)
                    seen_courses.add(course_id)

        # Check for a link to additional courses in this category (existing logic)
        links = []
        if a.find_parent('table'):
            links = a.find_parent('table').find_all('a', href=lambda h: h and 'p_list_courses' in h)

        # If no links found, try a broader search in nearby elements
        if not links and a.parent:
            # Look in following siblings and their children
            for sibling in a.parent.find_next_siblings():
                links.extend(sibling.find_all('a', href=lambda h: h and 'p_list_courses' in h))

            # Also search in the next few elements after the anchor
            current_element = a
            for _ in range(15):  # Look through next 15 elements for Click links
                current_element = current_element.find_next()
                if not current_element:
                    break
                if current_element.name == 'a' and current_element.get('href') and 'p_list_courses' in current_element.get('href'):
                    links.append(current_element)

        for link in links:
            # Extract category from the link URL to double-check
            area_match = re.search(r'P_AREA=([^&]+)', link['href'])
            if area_match:
                area_code = area_match.group(1)
                # Override el_type if we have a more specific area code from the URL
                if '_CEL' in area_code or '_COR' in area_code or '_CE1' in area_code or '_C1' in area_code:
                    el_type = 'core'
                elif '_CE2' in area_code or '_PHL' in area_code or '_MEL' in area_code or '_C2' in area_code:
                    el_type = 'extra_attribute'
                elif '_REQ' in area_code:
                    el_type = 'required'
                elif '_AEL' in area_code or '_ARE' in area_code:
                    el_type = 'area'
                elif '_FEL' in area_code or '_FRE' in area_code:
                    el_type = 'free'
                elif 'UC_' in area_code:
                    el_type = 'university'
                elif '_PHL' in area_code or '_MEL' in area_code:
                    el_type = 'required'
                else:
                    el_type = 'unknown'
            list_url = urljoin(BASE, link['href'])
            new_rows = crawl_list(list_url, el_type)
            for row in new_rows:
                course_id = f"{row['Major']}{row['Code']}"
                if course_id not in seen_courses:
                    results.append(row)
                    seen_courses.add(course_id)

    # Add a fallback method to catch links that might have been missed
    # Look for all "Click" links throughout the page
    for click_link in soup.find_all('a', href=lambda h: h and 'p_list_courses' in h):
        area_match = re.search(r'P_AREA=([^&]+)', click_link['href'])
        if area_match:
            area_code = area_match.group(1)
            # Determine category from area code
            if '_CEL' in area_code or '_COR' in area_code or '_CE1' in area_code or '_CE2' in area_code or '_C1' in area_code or '_C2' in area_code:
                el_type = 'core'
            elif '_REQ' in area_code:
                el_type = 'required'
            elif '_AEL' in area_code or '_ARE' in area_code:
                el_type = 'area'
            elif '_FEL' in area_code or '_FRE' in area_code:
                el_type = 'free'
            elif 'UC_' in area_code:
                el_type = 'university'
            elif '_PHL' in area_code or '_MEL' in area_code:
                el_type = 'required'
            else:
                # Default to if unknown
                el_type = 'unknown'

            list_url = urljoin(BASE, click_link['href'])
            new_rows = crawl_list(list_url, el_type)
            for row in new_rows:
                course_id = f"{row['Major']}{row['Code']}"
                if course_id not in seen_courses:
                    results.append(row)
                    seen_courses.add(course_id)

    return results


def main():

    os.makedirs(COURSES_DIR, exist_ok=True)

    programs = get_program_codes()
    for code, fname in PROGRAM_FILES.items():
        if code not in programs:
            continue
        term = get_latest_term(code)
        if not term:
            continue
        data = crawl_program(code, term)
        full_path = os.path.join(COURSES_DIR, fname)
        if not data:
            print(f'No data found for {code} ({fname})')
            continue
        with open(full_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f'Updated {fname} with {len(data)} records')

    # Optionally run update_credits.py after updating course files
    print("\nRunning update_credits.py to update credits in JSON files...\n")
    subprocess.run(['python', 'update_credits.py'], check=True)


if __name__ == '__main__':
    main()
