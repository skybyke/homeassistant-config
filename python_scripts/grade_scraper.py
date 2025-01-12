#!/usr/bin/env python3
import sys
import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
import os
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class PowerSchoolGradeScraper:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://ps.saugatuckps.com"
        # Add headers to mimic a browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })

    def login(self, username, password):
        try:
            logger.info("Getting initial page...")
            initial_response = self.session.get(f"{self.base_url}/public/home.html", timeout=30)
            if not initial_response.ok:
                logger.error(f"Failed to get initial page: {initial_response.status_code}")
                return False

            logger.info("Submitting login...")
            login_data = {
                'account': username,
                'pw': password,
                'ldappassword': password,
            }

            login_response = self.session.post(
                f"{self.base_url}/guardian/home.html",
                data=login_data,
                allow_redirects=True,
                timeout=30
            )

            logger.info(f"Login response status: {login_response.status_code}")

            if 'Grades and Attendance' in login_response.text:
                logger.info("Login successful!")
                return True
            else:
                logger.error("Login failed - couldn't access grades page")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during login: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during login: {str(e)}")
            return False

    def find_current_term_column(self, table):
        try:
            rows = table.find_all('tr')[2:]  # Skip header rows
            grade_columns = {}
            
            for row in rows:
                cells = row.find_all('td')
                for i, cell in enumerate(cells):
                    grade_link = cell.find('a', class_='bold')
                    if grade_link:
                        grade_text = grade_link.get_text(strip=True)
                        if re.match(r'[A-D][+-]?\d+', grade_text):
                            grade_columns[i] = grade_text
                            logger.debug(f"Found grade in column {i}: {grade_text}")
            
            if grade_columns:
                current_term_index = max(grade_columns.keys())
                logger.info(f"Current term index: {current_term_index}")
                return current_term_index
            return None

        except Exception as e:
            logger.error(f"Error finding current term column: {str(e)}")
            return None

    def parse_grade(self, grade_text):
        try:
            grade_text = grade_text.strip()
            
            if '\n' in grade_text:
                parts = grade_text.split('\n')
                return parts[0].strip(), parts[1].strip()
            
            match = re.match(r'([A-D][+-]?)(\d+)', grade_text)
            if match:
                return match.group(1), match.group(2)
                
            return None, None

        except Exception as e:
            logger.error(f"Error parsing grade text '{grade_text}': {str(e)}")
            return None, None

    def extract_grades(self, html_content):
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            grades = []
            
            # Find the grade table
            table = soup.find('table', {'class': 'linkDescList'})
            if not table:
                logger.error("Could not find grade table")
                return []

            current_term_index = self.find_current_term_column(table)
            if current_term_index is None:
                logger.error("Could not find current term column")
                return []

            rows = table.find_all('tr')[2:]  # Skip header rows
            for row in rows:
                cells = row.find_all('td')
                if len(cells) <= current_term_index:
                    continue

                course_cell = cells[11] if len(cells) > 11 else None
                if not course_cell:
                    continue

                course_text = course_cell.get_text(strip=True)
                course_name = re.split(r'\d', course_text)[0].strip()

                grade_cell = cells[current_term_index]
                grade_link = grade_cell.find('a', class_='bold')
                
                if grade_link and not grade_link.get_text().strip().startswith('['):
                    grade_text = grade_link.get_text(strip=True)
                    letter_grade, percentage = self.parse_grade(grade_text)
                    if letter_grade and percentage:
                        grades.append({
                            'class': course_name,
                            'grade': letter_grade,
                            'percentage': percentage
                        })
                        logger.info(f"Processed grade for {course_name}: {letter_grade} ({percentage})")

            return grades

        except Exception as e:
            logger.error(f"Error extracting grades: {str(e)}")
            return []

    def get_grades(self):
        try:
            logger.info("Fetching grades page...")
            response = self.session.get(f"{self.base_url}/guardian/home.html", timeout=30)
            
            if not response.ok:
                logger.error(f"Failed to get grades page: {response.status_code}")
                return []
                
            grades = self.extract_grades(response.text)
            
            if not grades:
                logger.warning("No grades found in the response")
                
            return grades

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error getting grades: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting grades: {str(e)}")
            return []

def main():
    try:
        # Ensure we're in the correct directory
        script_dir = Path(__file__).parent.absolute()
        os.chdir(script_dir)
        
        logger.info("Starting grade scraping process...")
        
        scraper = PowerSchoolGradeScraper()
        username = "MCA.Klynstra"
        password = "MCApowe2024!"
        
        if scraper.login(username, password):
            grades = scraper.get_grades()
            
            data = {
                "grades": grades,
                "last_updated": datetime.now().isoformat()
            }
            
            # Save to JSON file in the same directory as the script
            output_file = script_dir / 'grades.json'
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2)
                logger.info(f"Grades saved to {output_file}")
            
            if grades:
                logger.info("Grades retrieved successfully:")
                for grade in grades:
                    logger.info(f"{grade['class']}: {grade['grade']} ({grade['percentage'})")
                sys.exit(0)
            else:
                logger.error("No grades were found!")
                sys.exit(1)
        else:
            logger.error("Failed to login")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Critical error in main: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()