import os
import shutil
import re
root = os.path.dirname(os.path.abspath(__file__))
path = "/home/nobackup/eduard/tmp/x"

def part1():
    for file in os.listdir(path):
        print(file)
        name = re.sub("S3.*-week-","",file)
        shutil.copy(f"{path}/{file}", f"{root}/senec_data_2021/{name}")
        print(name)

def part2():
    newpath = f"{root}/senec_data_2021/"
    for i in range(54):
        name = f"{i}-2021.csv"
        if not os.path.isfile(f"{newpath}/{name}"):
            print(f"{name} not found")
        else:
            print(f"{name} found")

    pass

part1()