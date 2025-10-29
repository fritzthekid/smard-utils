from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import os
import pandas as pd
from locals import locals
from datetime import datetime

import time

class SenecDownloader:

    def __init__(self):
        options = Options()
        options.headless = True
        self.chrome = webdriver.Chrome(options=options)
        time.sleep(1)
        print("Chrome loaded")

    def login(self,password):
        # Chromium browser location, below location is for my PC, 
        # you have to enter the file location for your PC
        loginurl = "https://www.mein-senec.de/endkunde/oauth2/authorization/endkunde-portal"
        self.chrome.get(loginurl)
        time.sleep(1)
        self.chrome.find_element(By.ID,"username").send_keys("eduard.moser@gmx.de")
        self.chrome.find_element(By.ID,"password").send_keys(password)
        self.chrome.find_element(By.ID,"kc-login").click()
        time.sleep(1)
        print("login down, success?")

    # https://mein-senec.de/endkunde/api/statistischeDaten/download?anlageNummer=0&woche=38&jahr=2025
    def download_page(self,year):
        base_url="https://mein-senec.de/endkunde/api/statistischeDaten/"

        # urlretrieve(csv_url, "x.csv")
        for i in range(54):
            csv_url = base_url + f"download?anlageNummer=0&woche={i}&jahr={year}"
            try:
                self.chrome.get(csv_url)
                time.sleep(1)
            except Exception as e:
                print("Exception ", e)
            self.chrome.get(csv_url)
            time.sleep(1)

        print("Pages Downloaded")
        pass

def main(year):
    # password = os.environ("PASSWORD")
    # password = input("password: ")
    password = locals[1]
    senec = SenecDownloader()
    senec.login(password)
    senec.download_page(year)
    senec.chrome.close()

def combine_data(year):
    path=f"{os.path.abspath(os.path.dirname(__file__))}/senec_data_{year}"
    for i in range(1,54):
        file = f"{path}/S3997766842486038808793653-week-{i}-{year}.csv"
        if i == 1:
            df = pd.read_csv(file, sep=';', decimal=',')
            ddf = df
        else:
            df = pd.read_csv(file, sep=';', decimal=',')
            ddf = pd.concat([ddf,df], ignore_index=True)
        pass
    ddf.to_csv(f"{path}/{year}-combine.csv")
    pass

if __name__ == "__main__":
    year = 2023
    # main(year)
    combine_data(year)
    pass


