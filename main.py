import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin,urlparse
import re
import base64
from flask import *
from flask_cors import CORS
import json

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
options = Options()
options.add_argument("--headless=new")

from webdriver_manager.chrome import ChromeDriverManager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import ToolsRoutes


# Constants
nonrenw_energytocarbon = 442 #g/kWh
renw_energytocarbon = 50 #g/kWh
datatoenergy = 0.81 #kWh/GB
returning_customer = 0.75 + 0.02*0.25


def fetch_resource_size(resource_url):
    response = requests.get(resource_url)
    if response.status_code == 200:
        content_length = response.headers.get('Content-Length')
        if content_length:
          return int(content_length)
        else:
          return len(response.content)
    else:
        return 0


def getsource(tag):
    src = None
    if not src: src = tag.get('src')
    if not src: src = tag.get('data-src')
    if not src: src = tag.get('data-gt-lazy-src')
    if not src: src = tag.get('href')
    if not src: src = tag.get('xlink:href')
    if not src: src = tag.get('poster')
    if not src: src = tag.get('srcset')
    if not src: src = tag.get('data-url')
    if not src: src = tag.get('data-example')
    if not src: src = tag.get('action')
    if src:
        if src.startswith("data:image/"): return None
    return src

def calculate_data_transfer(url):
    css_size_bytes = 0
    font_size_bytes = 0
    js_size_bytes = 0
    media_size_bytes = 0
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.get(url)
    html_content = driver.page_source
    driver.quit()
    soup = BeautifulSoup(html_content, 'html.parser')
    if True:
        html_size_bytes = len(html_content)
        # Fetch CSS files and estimate data transfer
        for link_tag in soup.find_all('link', rel='stylesheet'):
            src = getsource(link_tag)
            if src:
                css_url = urljoin(url, src)
                css_content = requests.get(css_url).content
                css_size_bytes += len(css_content)
                # Parse CSS content to find resource URLs and font file URLs
                resource_and_font_urls = re.findall(r'url\((.*?)\)', css_content.decode('utf-8'))
                for res_or_font_url in resource_and_font_urls:
                    abs_url = urljoin(css_url, res_or_font_url.strip('\'"'))
                    if abs_url.startswith('data:'):
                        continue
                    resource_or_font_size = fetch_resource_size(abs_url)
                    font_size_bytes += resource_or_font_size
                    
        # Fetch JS files and estimate data transfer
        for script_tag in soup.find_all('script'):
            src = getsource(script_tag)
            if src:
                js_url = urljoin(url, src)
                js_content = requests.get(js_url).content
                js_size_bytes += len(js_content)
                
                # Parse JS content to find video and audio URLs
                resource_urls = re.findall(r'src="(.*?)"', js_content.decode('utf-8'))
                for res_url in resource_urls:
                    if res_url.startswith(('data:', 'about:')):
                        continue  # Skip data URI schemes
                    abs_url = urljoin(js_url, res_url)
                    res_size = fetch_resource_size(abs_url)
                    js_size_bytes += res_size
                    
        # Fetch video and audio elements
        for video_tag in soup.find_all('video'):
            src = getsource(video_tag)
            if src:
                video_url = urljoin(url, src)
                video_size = fetch_resource_size(video_url)
                media_size_bytes += video_size

        
        for audio_tag in soup.find_all('audio'):
            src = getsource(audio_tag)
            if src:
                audio_url = urljoin(url, src)
                audio_size = fetch_resource_size(audio_url)
                media_size_bytes += audio_size

        for img_tag in soup.find_all('img'):
            src = getsource(img_tag)
            if src:
                image_url = urljoin(url, src)
                image_size = fetch_resource_size(image_url)
                media_size_bytes += image_size
        
        css_transfer_gb = css_size_bytes / (1024 ** 3)
        font_transfer_gb = font_size_bytes / (1024 ** 3)
        js_transfer_gb = js_size_bytes / (1024 ** 3)
        media_transfer_gb = media_size_bytes / (1024 ** 3)
        html_transfer_gb = html_size_bytes / (1024 ** 3)
        return css_transfer_gb, font_transfer_gb, js_transfer_gb, media_transfer_gb, html_transfer_gb
    else:
        raise Exception(f"Failed to fetch website content. Status code: {response.status_code}")




def check_green_website(url):
    parsed_url = urlparse(url).netloc
    url = f"https://api.thegreenwebfoundation.org/api/v3/greencheck/{parsed_url}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data["green"]
    else:
        return False

def calculate_carbon(data,green):
    return nonrenw_energytocarbon*datatoenergy*data*returning_customer

def cal_facts(Carbon):
    s = ["Check fact"]
    visits = 10000
    gm_to_kg = 0.001
    tree_absorb = 1.81   #kg absorbed per month
    car_consume = 0.17
    flight_consume = 0.15
    earth_cir = 40075

    tree_num = round( (Carbon*visits*gm_to_kg)/tree_absorb)
    tree_fact = f"Every 10,000 visits to this website is equivalent to the carbon dioxide absorbed by {tree_num} trees in one month."
    s.append(tree_fact)

    if Carbon < 8:
        car_num = round( (Carbon*visits*gm_to_kg)/car_consume, 1)
        car_fact = f"Every 10,000 visits to this website is equivalent to the carbon dioxide released by {car_num} kms of car driving."
        s.append(car_fact)
    else:
        fly_num = round( ((Carbon*visits*gm_to_kg*100)/flight_consume)/earth_cir, 1)
        fly_fact = f"Every 10,000 visits to this website is equivalent to the carbon dioxide released by covering {fly_num}% of earth circumference in flight."
        s.append(fly_fact)

    return s



def calculate_footprint(web_url):
    try:
        data_gb = calculate_data_transfer(web_url)
        totat_data = sum(data_gb)
        green = check_green_website(web_url)
        carbon = calculate_carbon(totat_data, green)
        fact = cal_facts(carbon)
        result = {
            'check':1,
            'css_data_mb': round(data_gb[0]*1024,3),
            'font_data_mb': round(data_gb[1]*1024,3),
            'js_data_mb': round(data_gb[2]*1024,3),
            'media_data_mb': round(data_gb[3]*1024,3),
            'html_data_mb': round(data_gb[4]*1024,3),
            'total_data_mb': round(totat_data*1024,3),
            'Carbon_footprint':carbon,
            'Green_hosting': green,
            'fact1': fact[1],
            'fact2': fact[2],
        }
        return result
    except Exception as e:
        result = {
            'check':0,
            'css_data_mb': 0.0,
            'font_data_mb': 0.0,
            'js_data_mb': 0.0,
            'media_data_mb': 0.0,
            'html_data_mb': 0.0,
            'total_data_mb': 0.0,
            'Carbon_footprint': 0.0,
            'Green_hosting': False,
            'fact1': "None",
            'fact2': "None",
        }
        return result


app = Flask(_name_)
CORS(app)
@app.route('/', methods=['GET', 'POST'])
def handle_request():
    text = str(request.args.get('input'))
    result = calculate_footprint(text)
    json_dump = json.dumps(result)
    return json_dump

if _name_ == '_main_':
    app.run(port=1234)
