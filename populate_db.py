import shutil
from io import BytesIO
from PIL import Image
import base64
import pandas as pd
import requests
from datetime import datetime
import os
import psycopg2
import csv

ENGLISH_EXCLUSIVE_EXPANSIONS = {'B2', 'BEST', 'BOO', 'BOO24', 'DCR', 'FUT20', 'GC', 'GH', 'LC', 'LTR', 'LTR_RC', 'MCD14', 'PK', 'RM', 'SI', 'SV', 'SV_SH', 'TRR'}
FRENCH_EXCLUSIVE_EXPANSIONS = {'MCD19F'}
EU_LANGUAGES = ['ITA', 'ENG', 'FRE', 'SPA', 'GER']

def move_file(source_path, destination_folder):
    # Create the destination folder if it doesn't exist
    os.makedirs(destination_folder, exist_ok=True)
    # Get the filename from the source path
    filename = os.path.basename(source_path)
    # Construct the destination path
    destination_path = os.path.join(destination_folder, filename)
    # Move the file
    shutil.move(source_path, destination_path)

def get_or_insert_illustrator(curr, illustrator):
  illustrator_id = None
  if not illustrator or pd.isna(illustrator):
    return None
  curr.execute("SELECT name FROM Illustrator WHERE name = %s", (illustrator,)) # check if it exists
  illustrator_id = curr.fetchone()

  if illustrator_id is None:
    curr.execute("INSERT INTO illustrator (name) VALUES (%s) RETURNING name", (illustrator,)) # insert if it doesn't exist
    illustrator_id = curr.fetchone()[0]
  print(f'\tCard\'s illustrator: {illustrator}')
  return illustrator_id

def download_media(url):
  if pd.isna(url): return None
  response = requests.get(url)
  return BytesIO(response.content)


def convert_date_format(date_string):
#     try:
#         return datetime.strptime(date_string, '%Y-%m-%d')
#     except ValueError:
#         # try:
#           return datetime.strptime(date_string, '%m/%d/%Y')
#         # except ValueError:
  return datetime.strptime(date_string, '%Y-%m-%d')


def get_super_expansion(filename):
    parts = filename.split('_')
    if len(parts) > 3:
        return parts[2]
    else:
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

def create_sets_dictionary(file_path):
    sets_dict = {}
    df = pd.read_excel(file_path)
    for index, row in df.iterrows():
        inglese = row['Inglese']
        italiano = row['Italiano']

        if pd.notna(italiano):  # Ignore rows with missing values
            sets_dict[inglese] = italiano
        else:
          sets_dict[inglese] = inglese
    return sets_dict

# Cards population

def populate_cardtype(conn, cursor, expansion, cards_path, save_image_path):
  df = pd.read_csv(cards_path, sep=',', encoding='latin1')
  unnumbered_index = 1
  for index, row in df.iterrows():
    card_name = row['card_name']
    rarity = row['rarity']
    if pd.isna(row['number']):
      row['number'] = 'unnumbered_'+str(unnumbered_index)
      unnumbered_index += 1
    number = row['number']
    illustrator = row.get('illustrator', None) # returns None if the column illustrator does not exist
    alt_versions = row['alternate versions']
    image_url = row['image']
    print(f'\tInserting card {number}')

    # Populate AlternateVersion table
    alt_versions_list = [version.strip().strip("'") for version in alt_versions.strip('[]').split(',')]
    alt_versions_list.append('default')
    for version in alt_versions_list:
      if version:

        cursor.execute('INSERT INTO AlternateVersion (version) VALUES (%s) ON CONFLICT DO NOTHING', (version,))

    # Populate Rarity table
    cursor.execute('INSERT INTO Rarity (name) VALUES (%s) ON CONFLICT DO NOTHING', (rarity,))

    # Download and store the image # not needed, downloaded in pokellector_scraper
  #  image_response = requests.get(image_url)
   # image_data = image_response.content if image_response.status_code == 200 else None

    base_cards_path = f'./expansion_images/{expansion}/cards'
    os.makedirs(base_cards_path, exist_ok=True)
    image_path = base_cards_path + f'/{number}.webp'
    #save_image_to_file(image_data, image_path)

    # Populate CardType table
    if illustrator and pd.notna(illustrator):
      print(f"Inserting new illustrator {illustrator}")
      get_or_insert_illustrator(cursor, illustrator)
      cursor.execute('''
          INSERT INTO CardType (number, expansion, illustrator, name, rarity, image_path)
          VALUES (%s, %s, %s, %s, %s, %s)
      ''', (number, expansion, illustrator, card_name, rarity, image_path))
    else:
      cursor.execute('''
          INSERT INTO CardType (number, expansion, name, rarity, image_path)
          VALUES (%s, %s, %s, %s, %s)
      ''', (number, expansion, card_name, rarity, image_path))
    for version in alt_versions_list:
      if version:
        # Associate each card to a list of possible versioncardtype
        cursor.execute('INSERT INTO versionCardType (version, card_number, card_expansion) VALUES (%s, %s, %s)', (version, number, expansion))
    print(f'\tAdded a new card: {card_name}')
  conn.commit()
  new_cards_path = os.path.join(os.path.dirname(cards_path), 'processed cards')
  move_file(cards_path, new_cards_path)

def populate_table_from_csv(conn, cursor, set_path, cards_path, is_jap, sets_dict, default_symbol_image_url='https://static.tcgcollector.com/build/images/default-expansion-logo-500x256.ef41d58e.png'):
    df = pd.read_csv(set_path, delimiter=',', encoding='latin1')

    super_expansion = get_super_expansion(os.path.basename(set_path))
    for index, row in df.iterrows():
        print('Inserting '+ str(row['name'])+' from '+set_path)
        if not(is_jap):
          if row['name'] == 151:
            italian_name = 151
          elif row['name'].startswith("McDonald's Collection"):
            italian_name = row['name']
          else:
            parts = row['name'].split('-')
            if len(parts)==2:
              s,sub = row['name'].split('-')[0].strip(), row['name'].split('-')[1].strip()
              italian_name = sets_dict[s] + ' - ' + sub
            else:
                italian_name = row['italian_name']
                if pd.isna(italian_name):
                  try:
                    italian_name = sets_dict[row['Italiano']]
                    if pd.isna(italian_name):
                      italian_name = row['name']
                  except KeyError:
                    italian_name = row['name']
        id = row['id']
        name = row['name']
        release_date = row['release date']
        main_card_number = row['cards #']
        generation = row['generation']
        if generation.endswith(' Series'):
            generation = generation.replace(' Series', '')
        elif generation.endswith(' Era'):
            generation = generation.replace(' Era', '')
        if generation == 'Black & Whit':
          generation = 'Black & White' # idk why
        icon_url = row['icon_image']
        symbol_url = row['symbol_image'] if pd.notna(row['symbol_image']) else default_symbol_image_url

        release_date = convert_date_format(release_date)  # Convert date format

        if release_date is None:
            print(f"Invalid date format: {row['release date']} in CSV: {set_path}")
            continue

        icon = download_media(icon_url)
        symbol = download_media(symbol_url)

        expansion_path = f'./expansion_images/{id}'
        os.makedirs(expansion_path, exist_ok=True)

        icon_path = expansion_path + '/icon.webp' if icon else None
        symbol_path = expansion_path + '/symbol.webp' if symbol else None

        ### now the image download logic is handled by the scraper
        # if icon:
        #   save_image_to_file(icon, icon_path)
        # if symbol:
        #   save_image_to_file(symbol, symbol_path)

        #CHECK IF THE MAIN_CARD_NUMBER IS ACTUALLY INSERTED!
        cursor.execute(
            "INSERT INTO CardExpansion (id, name, release_date, main_set_number, generation, super_expansion, icon_path, symbol_path) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (id, name, release_date, main_card_number, generation, super_expansion, icon_path, symbol_path)
        )
        if not(is_jap):
          cursor.execute(
              "INSERT INTO CardExpansionWorld (id, italian_name) VALUES (%s, %s)", (id, italian_name)
          )
        else:
          cursor.execute(
              "INSERT INTO CardExpansionJap (id) VALUES (%s)", (id,)
          )
        print(f"Added {row['name']}!")

        populate_cardtype(conn, cursor, row['id'], cards_path, expansion_path)

        # Move the set to the 'processed' subfolder
        new_set_path = os.path.join(os.path.dirname(set_path), 'processed sets')
        move_file(set_path, new_set_path)

        conn.commit()

def get_release_date(entry):
    return entry[4]  # Index 4 corresponds to the 'release date' attribute in my CSV format

def populate_expansion_table(db_params, sets_path, all_sets_cards_path, is_jap, all_sets_path=None):
    print('### START POPULATING! ###')
    # Connect to the PostgreSQL database
    conn = psycopg2.connect(**db_params)
    cursor = conn.cursor()

    sets_dict = create_sets_dictionary(all_sets_path) if all_sets_path else None

    # List to store file details
    file_details = []

    # Collect file details from each .csv file
    for filename in sorted(os.listdir(sets_path)):
        if filename.endswith('.csv'):
            set_path = os.path.join(sets_path, filename)
            with open(set_path, 'r') as csv_file:
                csv_reader = csv.DictReader(csv_file, delimiter=',')
                for row in csv_reader:
                    file_details.append({
                        'filename': filename,
                        'release_date': convert_date_format(row['release date']),
                        'name': row['name']
                    })

    # Sort the file details by release_date and then by name
    sorted_file_details = sorted(file_details, key=lambda x: (x['release_date'], x['name']))

    for file_detail in sorted_file_details:
        filename = file_detail['filename']
        set_path = os.path.join(sets_path, filename)
        df = pd.read_csv(set_path, encoding='latin1')
        cards_path = os.path.join(all_sets_cards_path, filename.split('.')[0]+'_cards.csv')
        populate_table_from_csv(conn, cursor, set_path, cards_path, is_jap, sets_dict)

    # Close the database connection
    cursor.close()
    conn.close()
    print("Expansion table populated successfully!")

def get_japexpansions(db_params):
  conn = psycopg2.connect(**db_params)
  cursor = conn.cursor()
  try:
    # Execute a SELECT query to fetch the cardexpansionjap.id values
    cursor.execute("""
        SELECT id
        FROM cardexpansionjap
        WHERE NOT EXISTS (
          SELECT 1
          FROM allowedexpansionlanguage
          WHERE allowedexpansionlanguage.expansion = cardexpansionjap.id
        )
    """)
    # Fetch all the results
    rows = cursor.fetchall()
    # Extract the ids and put them in a list
    id_list = [row[0] for row in rows]

    return id_list
  except Exception as e:
    print(f"Error: {e}")

def get_worldexpansions(db_params):
  conn = psycopg2.connect(**db_params)
  cursor = conn.cursor()
  try:
    # Execute a SELECT query to fetch the cardexpansionworld.id values
    cursor.execute("""
      SELECT id
      FROM cardexpansionworld
      WHERE NOT EXISTS (
          SELECT 1
          FROM allowedexpansionlanguage
          WHERE allowedexpansionlanguage.expansion = cardexpansionworld.id
        )
    """)
    # Fetch all the results
    rows = cursor.fetchall()
    # Extract the ids and put them in a list
    id_list = [row[0] for row in rows]

    return id_list
  except Exception as e:
    print(f"Error: {e}")

def insert_allowedexpansionlanguage(db_params, expansions_list, languages):
  conn = psycopg2.connect(**db_params)
  cursor = conn.cursor()
  try:
    for expansion_id in expansions_list:
      for language_id in languages:
        # Execute an INSERT query to insert into allowedexpansionlanguage table
        cursor.execute(
            "INSERT INTO allowedexpansionlanguage (expansion, language) VALUES (%s, %s)",
            (expansion_id, language_id)
        )

    # Commit the changes to the database
    conn.commit()

  except Exception as e:
    # Rollback the transaction in case of an error
    conn.rollback()
    print(f"Error: {e}")

def get_expansions_missing_language(db_params):
    worldexpansions = get_worldexpansions(db_params)

   # Print the results
    missing_english_expansions = [expansion for expansion in ENGLISH_EXCLUSIVE_EXPANSIONS if expansion not in worldexpansions]
   # print("Missing English expansions:", missing_english_expansions)
    missing_french_expansions = [expansion for expansion in FRENCH_EXCLUSIVE_EXPANSIONS if expansion not in worldexpansions]
   # print("Missing French expansions:", missing_french_expansions)

    non_exclusive_language_expansions = worldexpansions.copy()

    for expansion in ENGLISH_EXCLUSIVE_EXPANSIONS:
        if expansion in non_exclusive_language_expansions:
            print('removed '+expansion)
            non_exclusive_language_expansions.remove(expansion)

    for expansion in FRENCH_EXCLUSIVE_EXPANSIONS:
        if expansion in non_exclusive_language_expansions:
            print('removed '+expansion)
            non_exclusive_language_expansions.remove(expansion)

    return non_exclusive_language_expansions

def insert_eu_languages(db_params):
    non_exclusive_language_expansions = get_expansions_missing_language(db_params)
    insert_allowedexpansionlanguage(db_params, non_exclusive_language_expansions, EU_LANGUAGES)

def insert_jp_language(db_params):
   jap_expansions = get_japexpansions(db_params)
   insert_allowedexpansionlanguage(db_params, jap_expansions, ['JAP'])
    