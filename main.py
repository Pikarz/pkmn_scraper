
import time
import os

from pokellector_scraper import scrape_card_info, save_data, scrape_set
from populate_db import populate_expansion_table, insert_jp_language, insert_eu_languages

POKELLECTOR_URL = 'https://www.pokellector.com/'
DB_PARAMS = {
    'host': '192.168.1.2',
    'port': '5432',
    'database': 'cardmaster',
    'user': 'nemo',
    'password': '322322'
}

def scrape_and_populate(expansions, save_path):
    ## LIST SET SCRAPER
    wait_time = 1

    # Check consistency
    for expansion_dict in expansions:
        italian_name = expansion_dict.get('italian_name', '') # either get the value or sets it to empty string
        is_jap = expansion_dict['is_jap']
        assert (not is_jap or (len(italian_name) == 0)), 'A japanese expansion cannot have an italian name'

    for expansion_dict in expansions:
        data = {}
        set_url = expansion_dict['url']
        generation = expansion_dict['generation']
        italian_name = expansion_dict.get('italian_name', '') # either get the value or sets it to empty string
        is_jap = expansion_dict['is_jap']

        # Scraping + saving info
        set_id, set_name, number_of_cards, number_of_secret_cards, formatted_release_date, card_urls, icon_image, symbol_image = scrape_set(POKELLECTOR_URL+set_url)
        data[set_id] = {}
        data[set_id]['info'] = [set_id, set_name, number_of_cards, number_of_secret_cards, formatted_release_date, icon_image, symbol_image, generation, italian_name]
        data[set_id]['cards'] = []
        for card_url in card_urls:
            card_info = scrape_card_info(card_url, set_id)
            data[set_id]['cards'].append(card_info)
            time.sleep(wait_time)
        save_data(data, save_path, is_jap)
        data = {}

        sets_path = save_path + '/sets/'
        all_cards_path = save_path + '/cards/'

        # Actual populate of the database
        populate_expansion_table(DB_PARAMS, sets_path, all_cards_path, is_jap)

        if is_jap:
            insert_jp_language(DB_PARAMS)
        else:
            insert_eu_languages(DB_PARAMS)

if __name__ == '__main__':
    '''List of dictionaries where:
        url: is the pokellector url of the expansion without the domain, IE,'/Base-Set-Expansion/',
        generation: is the generation of the corresponding expansion, IE, 'Scarlet & Violet',
        italian_name: is the italian name of the expansion. Must be empty if is_jap is True,
        is_jap: is a boolean that specifies whether the corresponding expansion is japanese
    '''
    expansions = [
            {
                'url' : '/Super-Electric-Breaker-Expansion/',
                'generation': 'Scarlet & Violet',
                #'italian_name' : 'Dragon Discovery',
                'is_jap' : True
            }]
    
    save_path = 'G:/My Drive/pkmn_db/sets_new_insert/' ### REQUIRES OPEN DRIVE

    scrape_and_populate(expansions, save_path)
