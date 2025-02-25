from PIL import Image
from requests.exceptions import MissingSchema
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse, urljoin
from datetime import datetime
from io import BytesIO
import os  
import csv

IMAGES_PATH = 'Y:/cardmaster-project/frontend/pokecards/public/expansion_images/' # path to save the images of the cards and the set

def download_media(url):
  try:
    response = requests.get(url)
    return BytesIO(response.content)
  except MissingSchema:
    return None

def save_image_to_file(image_data, file_path, format='WEBP'):
  # Convert image_data to a BytesIO object if it's not already one
  if not isinstance(image_data, BytesIO):
      image_data = BytesIO(image_data)

  # Open the image using PIL
  image = Image.open(image_data)

  # Convert the image to WebP format
  image_webp_data = BytesIO()
  image.save(image_webp_data, format=format)

  # Save the WebP image data to the file
  with open(file_path, 'wb') as file:
      file.write(image_webp_data.getvalue())


def extract_alternative_versions(soup):
  # Initialize an empty list to store the extracted information
  alternate_versions = []
  # Find the header "Alternate Versions of this Card"
  header = soup.find("h1", string="Alternate Versions of this Card")
  # Extract the div containing the alternate card versions

  if header:
    div_cardlisting = header.find_next_sibling("div", class_="content cardlisting small")
    # Iterate through the div to extract the information
    for card_div in div_cardlisting.find_all("div", class_="card"):
        plaque_div = card_div.find("div", class_="plaque")
        if plaque_div:
            alternate_versions.append(plaque_div.text.strip())
  return alternate_versions

# Function to download the image and return its binary data
def download_image(url):
    response = requests.get(url)
    return response.content

def get_image(soup):
  image_url = soup.find('div', class_='card').find('img')['src']
  #image_data = download_image(image_url) # removed since i'll just store the urls
  return image_url

def extract_info(soup, label):
  div_elements = soup.select('.infoblurb div')
  for div in div_elements:
    strong_element = div.find('strong')
    if strong_element and re.search(rf'\b{label}\b', strong_element.text, re.IGNORECASE):
      return div.text.split(':', 1)[-1].strip()

def scrape_card_info(card_url, set_id):
  response = requests.get(card_url)
  if response.status_code == 200:
    soup = BeautifulSoup(response.content, "html.parser")

    h1_element = soup.find('h1', class_='icon set')
    for child in h1_element.find_all():
        child.extract()
    card_name = h1_element.get_text(strip=True)

    jpn_name = None
    rarity = None
    card_number = None

    # Extract the information for each label
    jpn_name = extract_info(soup, 'JPN')
    rarity = extract_info(soup, 'Rarity')
    card_number = extract_info(soup, 'Card').split('/')[0]

    # extract the alternate versions
    alt_versions = extract_alternative_versions(soup)
    # extract the image
    image_element = get_image(soup)

    image_response = requests.get(image_element)
    image_data = image_response.content if image_response.status_code == 200 else None
    base_cards_path = f'{IMAGES_PATH}/{set_id}/cards'
    os.makedirs(base_cards_path, exist_ok=True)
    image_path = base_cards_path + f'/{card_number}.webp'
    save_image_to_file(image_data, image_path)

    print('\tScraping card number: '+card_number)

    return {'card_name': card_name, 'jpn_name': jpn_name, 'rarity': rarity, 'number': card_number, 'alternate versions': alt_versions, 'image': image_element}
  else:
    print(f"Failed to retrieve data from {card_url}")
    return {}

def scrape_card_urls(set_url, soup):
    card_urls = []

    # Find all anchor tags with href attributes
    anchor_tags = soup.find_all('a', href=True)

    # Extract the base URL dynamically
    parsed_url = urlparse(set_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    for anchor_tag in anchor_tags:
        card_url = urljoin(base_url, anchor_tag['href'])
        if re.match(fr'{re.escape(base_url)}/.+Card-[a-zA-Z]*\d+[a-zA-Z]*$', card_url):
            card_urls.append(card_url)
    return card_urls

def scrape_icon_and_symbol_set(soup, id):
  icon_tag = soup.find('h1', class_='icon symbol').find('img', src=True)
  icon_url = icon_tag['src']
  #symbol_image = download_image(symbol_url) # i'll just store the urls and i'll scrape them later
  expansion_path = f'{IMAGES_PATH}/{id}'

  os.makedirs(expansion_path, exist_ok=True)
  symbol_tag = soup.find('meta', {'property': 'og:image'})
  symbol_url = symbol_tag['content']
  icon = download_media(icon_url)
  symbol = download_media(symbol_url)

  icon_path = expansion_path + '/icon.webp' if icon else None
  symbol_path = expansion_path + '/symbol.webp' if symbol else None

  if icon:
    save_image_to_file(icon, icon_path)
  if symbol:
    save_image_to_file(symbol, symbol_path)

  return [symbol_url, icon_url]


def scrape_name_and_id(soup):
    h1_element = soup.find('h1', class_='icon set')
    for child in h1_element.find_all():
      child.extract()
    set_name = h1_element.get_text(strip=True)

    set_meta_tag = soup.find('meta', attrs={'name': 'keywords'})
    # Extract the value of the "content" attribute
    set_content = set_meta_tag['content']
    # Get the last word before the character `"`
    set_id = set_content.split()[-1].rstrip(',')
    return set_id, set_name

def scrape_card_number(soup):
    # Extracting the desired information
    cards_element = soup.find('div', class_='cards')
    number_of_cards = cards_element.find_all('span')[1].text

    secret_element = cards_element.find('cite')
    number_of_secret_cards = None
    if secret_element:
      number_of_secret_cards = secret_element.text.split()[0].split('+')[1]
    return number_of_cards, number_of_secret_cards

def scrape_release_date(soup):
    #Find the span containing the release date month and day
    pattern = re.compile(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2}(st|nd|rd|th)$')
    release_date_span = soup.find('span', string=pattern)

    release_date = release_date_span.text.strip()
    release_date = re.sub(r'(st|nd|rd|th)', '', release_date)
    year = release_date_span.find_next('cite').text.strip()
    parsed_date = datetime.strptime(f"{release_date} {year}", "%b %d %Y")
    formatted_release_date = parsed_date.strftime("%Y-%m-%d")
    return formatted_release_date

def scrape_set(set_url):
  print("Scraping set: "+set_url)
  response = requests.get(set_url)
  if response.status_code == 200:
    soup = BeautifulSoup(response.text, 'html.parser')

    set_id, set_name = scrape_name_and_id(soup)
    number_of_cards, number_of_secret_cards = scrape_card_number(soup)
    formatted_release_date = scrape_release_date(soup)

    card_urls = scrape_card_urls(set_url, soup)
    icon_url, symbol_url = scrape_icon_and_symbol_set(soup, set_id)

    return set_id, set_name, number_of_cards, number_of_secret_cards, formatted_release_date, card_urls, icon_url, symbol_url
  else:
    print(f"Failed to retrieve data from {set_url}")
    return []
  
def extract_set_urls(url):
  response = requests.get(url)
  if response.status_code == 200:
    soup = BeautifulSoup(response.text, 'html.parser')
    set_urls = []
    # Find all anchor tags with class "button" and get their "href" attribute
    anchor_tags = soup.find_all('a', class_='button')

    for anchor_tag in anchor_tags:
        set_url = anchor_tag['href']
        set_urls.append(set_url)

    return set_urls
  else:
    print(f"Failed to retrieve data from {url}")
    return []

def save_data(data, save_path, is_jap):
  # Specify the file name and extension
  for set_name, set_data in data.items():
    csv_file_path_set = os.path.join(save_path, 'sets', 'pokemon_cards_' + set_name + '.csv')
    csv_file_path_set_cards = os.path.join(save_path, 'cards', 'pokemon_cards_' + set_name + '_cards.csv')
    set_info = set_data['info']
    cards_info = set_data['cards']

    with open(csv_file_path_set, 'w', newline='', encoding='utf-8') as file:
      writer = csv.writer(file)
      writer.writerow(['id', 'name', 'cards #', 'secret cards #', 'release date', 'icon_image', 'symbol_image', 'generation', 'italian_name' if not(is_jap) != 0 else '']) 
      writer.writerow(set_info)

    with open(csv_file_path_set_cards, 'w', newline='', encoding='utf-8') as file:
      writer = csv.writer(file)
      writer.writerow(['card_name', 'jpn_name', 'rarity', 'number', 'alternate versions', 'image'])
      for card in cards_info:
          writer.writerow([card['card_name'], card['jpn_name'], card['rarity'], card['number'], card['alternate versions'], card['image']])

