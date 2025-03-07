###
# Combines json files in data/diary into one large JSON
###

import os, sys, json

directory = "data/diary"
all_files = [file for file in os.listdir(directory) if os.path.isfile(os.path.join(directory, file))]
for i,v in enumerate(all_files):
    all_files[i] = os.path.join(directory,v)

print(all_files)

json_combined = list()

for jsonfile in all_files:
    with open(jsonfile, "r") as file:
        data = json.load(file)
        d = dict()
        d["date"] = jsonfile.strip(".json").strip(directory)
        d["meals"] = data
        json_combined.append(d)

## Create a chunk of jsons based on chunk_size
# 
#chunk_size=30
#for i in range(0,len(json_combined),chunk_size):
#    chunk = json_combined[i:i+chunk_size]
#    with open(f"chunk_{i//chunk_size + 1}.json", "w") as output_file:
#        json.dump(chunk, output_file, indent=4)

## Create a json with merged data from directory
with open("data/meals.json", "w") as file:
    json.dump(json_combined, file, indent=4)