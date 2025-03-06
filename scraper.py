# dependencies pip install requests beautifulsoup4 openai python-dotenv

import os
import requests
from bs4 import BeautifulSoup
import json
from openai import OpenAI
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API key from environment variable
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if not OPENAI_API_KEY:
    raise ValueError("Please set OPENAI_API_KEY in your .env file")

# Base URL 
MAIN_URL = "https://www.ca.gov/lafires/" 
SUBPAGES_TO_SCRAPE = 10  # Number of most relevant subpages

# Headers to mimic a browser request
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
}

# Directory to store scraped text files
OUTPUT_DIR = "lafires_scraped_texts"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

def get_page_content(url):
    try:
        print(f"Fetching {url}...")
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Get the page title
        title = soup.find('title')
        page_title = title.string.split('|')[0].strip() if title else None
        
        # Remove script, style, and header/footer elements
        for element in soup.find_all(['script', 'style', 'header', 'footer']):
            element.decompose()
            
        # Get main content
        main_content = soup.find('main')
        if main_content:
            # Clean up the text
            text = main_content.get_text(separator='\n', strip=True)
            lines = (line.strip() for line in text.splitlines())
            text = '\n'.join(line for line in lines if line)
            return text, soup, page_title
        else:
            print(f"No main content found in {url}")
            return None, soup, page_title
            
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None, None, None

def sanitize_filename(filename):
    # Remove or replace invalid filename characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    # Replace multiple spaces/underscores with single underscore
    filename = re.sub(r'[\s_]+', '_', filename)
    # Remove leading/trailing underscores and convert to lowercase
    return filename.strip('_').lower()

# Step 1: Fetch main page content
print("Fetching main page...")
main_text, main_soup, _ = get_page_content(MAIN_URL)

if main_soup is None:
    print(f"Failed to fetch {MAIN_URL}")
    exit(1)

# Step 2: Extract subpage links
print("Extracting links...")
subpage_links = []

# Look for specific sections we want to scrape based on the HTML structure
sections_to_scrape = [
    '/lafires/get-help-online/',
    '/lafires/get-help-in-person/',
    '/lafires/see-real-time-info/',
    '/lafires/start-your-recovery/',
    '/lafires/help-your-business/',
    '/lafires/volunteer/',
    '/lafires/cleanup-and-debris-removal/',
    '/lafires/recovery-services-finder/',
    '/lafires/track-progress/'
]

for link in main_soup.find_all('a', href=True):
    href = link['href']
    if any(section in href for section in sections_to_scrape):
        full_url = requests.compat.urljoin(MAIN_URL, href)
        if full_url not in subpage_links:
            subpage_links.append(full_url)
            print(f"Added link: {full_url}")

if not subpage_links:
    print("\nNo links found. Website structure might have changed.")
    exit(1)

print(f"\nFound {len(subpage_links)} links")

# Step 3: Use GPT to rank the most relevant subpages
prompt = f"""
Analyze these URLs from the LA Fires response site:
{subpage_links}

Return a JSON array of the URLs, sorted by most important recovery and assistance information first.
Format your response as a raw JSON array only, no markdown or other text.
"""

response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": "You are a helpful assistant that returns clean JSON arrays only, no markdown formatting."},
        {"role": "user", "content": prompt}
    ],
    temperature=0.3
)

try:
    # Clean the response content by removing markdown if present
    content = response.choices[0].message.content
    content = re.sub(r'^```json\s*|\s*```$', '', content.strip())
    ranked_links = json.loads(content)
    
    if not ranked_links:  # If GPT returns empty array, use original links
        print("GPT returned empty array, using original links")
        ranked_links = subpage_links
except json.JSONDecodeError as e:
    print(f"Failed to parse JSON from GPT response: {e}")
    print("Using original links instead")
    ranked_links = subpage_links

# Step 4: Scrape and save content from each relevant subpage
print("\nScraping pages...")
for i, subpage_url in enumerate(ranked_links):
    try:
        text_content, _, page_title = get_page_content(subpage_url)
        if text_content and page_title:
            # Create filename with priority and sanitized title
            priority_num = str(i + 1).zfill(2)  # Pad with leading zero for proper sorting
            sanitized_title = sanitize_filename(page_title)
            filename = f"priority_{priority_num}_{sanitized_title}.txt"
            filepath = os.path.join(OUTPUT_DIR, filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                # Add title and URL at the top of the file
                f.write(f"Title: {page_title}\n")
                f.write(f"URL: {subpage_url}\n")
                f.write(f"Priority: {i + 1}\n")
                f.write("-" * 80 + "\n\n")
                f.write(text_content)
            print(f"Saved: {filename}")
        else:
            print(f"Failed to fetch content from {subpage_url}")
    except Exception as e:
        print(f"Error scraping {subpage_url}: {e}")

print("\nScraping complete. Check the 'lafires_scraped_texts' folder.")