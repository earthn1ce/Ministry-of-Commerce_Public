
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pandas as pd
from flask import Flask, render_template, request, send_file, jsonify
import io
import os
from werkzeug.utils import secure_filename
import re

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def fetch_date_elements(url):
    try:
        # Fetch the HTML content
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        # Parse the HTML
        soup = BeautifulSoup(response.content, 'html.parser')

        # Try multiple strategies to find date elements - get more elements initially
        date_elements = []
        
        # Strategy 1: Find elements with class "date"
        date_elements = soup.find_all(class_='date', limit=20)  # Increased limit
        
        # Strategy 2: If no "date" class found, try common date-related classes
        if not date_elements:
            for class_name in ['time', 'pubtime', 'publish-time', 'date-time', 'datetime']:
                date_elements = soup.find_all(class_=class_name, limit=20)  # Increased limit
                if date_elements:
                    break
        
        # Strategy 3: Look for elements containing date patterns
        if not date_elements:
            date_pattern = re.compile(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{4}\.\d{1,2}\.\d{1,2}')
            all_elements = soup.find_all(string=date_pattern)
            date_elements = [elem.parent for elem in all_elements[:20]]  # Increased limit
        
        # Strategy 4: Look in common HTML tags that might contain dates
        if not date_elements:
            for tag in ['span', 'div', 'p', 'td']:
                potential_dates = soup.find_all(tag, string=re.compile(r'\d{4}'))
                if potential_dates:
                    date_elements = potential_dates[:20]  # Increased limit
                    break

        # Extract all date texts first (including repeats)
        all_date_texts = []
        for element in date_elements:
            if element:
                text = element.get_text(strip=True)
                # Extract date-like patterns from the text
                date_matches = re.findall(r'\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}|\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4}', text)
                if date_matches:
                    all_date_texts.extend(date_matches)
                elif text:
                    all_date_texts.append(text)
        
        # Parse all dates and sort them by date (latest first)
        parsed_dates_with_text = []
        date_formats = [
            "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d",
            "%m/%d/%Y", "%m-%d-%Y", "%d.%m.%Y", "%Y.%m.%d",
            "%d/%m/%y", "%d-%m-%y", "%y/%m/%d"
        ]
        
        for date_str in all_date_texts:
            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    parsed_dates_with_text.append((parsed_date, date_str))
                    break
                except ValueError:
                    continue
        
        # Sort by date (latest first)
        parsed_dates_with_text.sort(key=lambda x: x[0], reverse=True)
        
        # Get latest 5 unique dates while counting total publications
        seen_dates = set()
        unique_dates = []
        total_publications = 0
        
        for parsed_date, date_str in parsed_dates_with_text:
            date_key = parsed_date.date()  # Use date part only for comparison
            total_publications += 1  # Count every publication (including repeats)
            
            # Only add to unique_dates if we haven't seen this date before
            if date_key not in seen_dates:
                seen_dates.add(date_key)
                unique_dates.append(date_str)
            
            # Stop when we have encountered publications from 5 different unique dates
            if len(unique_dates) >= 5:
                # Continue counting publications until we've processed all publications 
                # from these 5 unique dates
                current_unique_count = len(unique_dates)
                remaining_publications = 0
                
                for remaining_parsed, remaining_str in parsed_dates_with_text[total_publications:]:
                    remaining_date_key = remaining_parsed.date()
                    if remaining_date_key in seen_dates:
                        remaining_publications += 1
                    else:
                        break  # Stop when we encounter a date outside our 5 unique dates
                
                total_publications += remaining_publications
                break
        
        return {
            'unique_dates': unique_dates,
            'total_publications': total_publications
        }

    except Exception as e:
        print(f"Error fetching URL {url}: {e}")
        return []

def parse_dates(date_list):
    # List of possible date formats to try
    date_formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d",
        "%m/%d/%Y", "%m-%d-%Y", "%d.%m.%Y", "%Y.%m.%d",
        "%d/%m/%y", "%d-%m-%y", "%y/%m/%d"
    ]
    
    dates = []
    for date_str in date_list:
        parsed = False
        for fmt in date_formats:
            try:
                date = datetime.strptime(date_str, fmt)
                dates.append(date)
                parsed = True
                break
            except ValueError:
                pass
        if not parsed:
            return None
    
    return dates

def calculate_date_gaps(dates):
    n = len(dates)
    if n < 2:
        return None, [], 0
    
    # Sort the dates in ascending order
    dates.sort()
    
    # Calculate the gaps in days between consecutive dates
    gaps = [(dates[j+1] - dates[j]).days for j in range(n-1)]
    
    # Sum the gaps
    sum_gaps = sum(gaps)
    
    # For exactly 5 dates, divide by 5; otherwise divide by number of gaps
    if n == 5:
        result = sum_gaps / 5
        divisor = 5
    else:
        result = sum_gaps / (n-1)
        divisor = n-1
    
    return result, gaps, divisor

def process_url(url):
    """Process a single URL and return detailed result information"""
    try:
        print(f"Processing URL: {url}")
        date_data = fetch_date_elements(url)
        
        # Handle the new return format
        if isinstance(date_data, dict):
            date_texts = date_data['unique_dates']
            total_publications = date_data['total_publications']
        else:
            # Fallback for old format (shouldn't happen but for safety)
            date_texts = date_data
            total_publications = len(date_texts)
        
        print(f"Found unique date texts: {date_texts}")
        print(f"Total publications (including repeats): {total_publications}")
        
        # Calculate publication metrics
        num_unique_dates = len(date_texts)
        unique_dates_for_calc = min(num_unique_dates, 5)  # Cap at 5 for denominator
        avg_publications_per_time = round(total_publications / unique_dates_for_calc, 2) if unique_dates_for_calc > 0 else 0
        sum_publications = total_publications  # Total publications including repeats
        
        if len(date_texts) >= 2:
            dates = parse_dates(date_texts)
            print(f"Parsed dates: {dates}")
            
            if dates:
                result, gaps, divisor = calculate_date_gaps(dates)
                if result is not None:
                    print(f"Result: {result}")
                    return {
                        'result': round(result, 2),
                        'num_dates': len(dates),
                        'dates_detected': [date.strftime('%Y-%m-%d') for date in sorted(dates, reverse=True)],
                        'gaps': list(reversed(gaps)),
                        'sum_gaps': sum(gaps),
                        'avg_publications_per_time': avg_publications_per_time,
                        'sum_publications': sum_publications,
                        'error': None
                    }
        
        print("Could not calculate - insufficient or unparseable dates")
        return {
            'result': "Error: Could not calculate",
            'num_dates': len(date_texts),
            'dates_detected': date_texts,
            'gaps': [],
            'sum_gaps': 0,
            'avg_publications_per_time': avg_publications_per_time,
            'sum_publications': sum_publications,
            'error': "Insufficient or unparseable dates"
        }
    
    except Exception as e:
        print(f"Exception processing {url}: {str(e)}")
        return {
            'result': f"Error: {str(e)}",
            'num_dates': 0,
            'dates_detected': [],
            'gaps': [],
            'sum_gaps': 0,
            'avg_publications_per_time': 0,
            'sum_publications': 0,
            'error': str(e)
        }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_urls', methods=['POST'])
def process_urls():
    try:
        urls = []
        
        # Check if file was uploaded
        if 'file' in request.files:
            file = request.files['file']
            if file.filename != '':
                # Read Excel file
                df = pd.read_excel(file)
                # Get the first column (assuming URLs are in the first column)
                urls = df.iloc[:, 0].dropna().tolist()
        
        # Check if URLs were pasted
        if 'urls_text' in request.form:
            urls_text = request.form['urls_text'].strip()
            if urls_text:
                # Split by both newlines and any whitespace, filter out empty strings
                url_lines = [line.strip() for line in urls_text.replace('\r\n', '\n').split('\n')]
                urls = [url for url in url_lines if url.strip() and url.startswith('http')]
                print(f"Parsed URLs from text: {urls}")
        
        if not urls:
            return jsonify({'error': 'No URLs provided'})
        
        # Process URLs and calculate results
        results = []
        for i, url in enumerate(urls):
            print(f"Processing {i+1}/{len(urls)}: {url}")
            result = process_url(url)
            results.append(result)
            print(f"Result for {url}: {result}")
        
        # Prepare response data
        response_data = []
        for url, result_data in zip(urls, results):
            if isinstance(result_data, dict):
                response_data.append({
                    'url': url,
                    'result': str(result_data['result']),
                    'num_dates': result_data['num_dates'],
                    'dates_detected': ', '.join(result_data['dates_detected']) if result_data['dates_detected'] else 'None',
                    'gaps': ', '.join(map(str, result_data['gaps'])) if result_data['gaps'] else 'None',
                    'sum_gaps': result_data['sum_gaps'],
                    'avg_publications_per_time': result_data.get('avg_publications_per_time', 0),
                    'sum_publications': result_data.get('sum_publications', 0)
                })
            else:
                # Handle old format (shouldn't happen but for safety)
                response_data.append({
                    'url': url,
                    'result': str(result_data),
                    'num_dates': 0,
                    'dates_detected': 'None',
                    'gaps': 'None',
                    'sum_gaps': 0,
                    'avg_publications_per_time': 0,
                    'sum_publications': 0
                })
        
        print(f"Final response data: {response_data}")
        
        # Return results as JSON for table display
        return jsonify({
            'success': True,
            'data': response_data
        })
    
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
