# food-diary
Place for food tracking scripts

`app.py`
Generates macros breakdown for a given JSON input file. For example:

```
$ python3 app.py 20240621python3 app.py data/diary/20240621.json 
{'calories': 1711.982598940107,
 'carbs': 172.02571154723708,
 'fat': 53.27771356060606,
 'protein': 135.4910061995722,
 'sodium': 1.296596180392157}
```

`merge.py`
Creates a merged `meals.json` file.

`trend.py`
Using `food.json` and `meals.json`, creates a couple plots.

`data/`
Contains template jsons, as well as general jsons that are both used and unused:

`data/diary`
All JSON files for food consumed are here. File names are by date. A `template.json` file also exists, which is what I used as a starting point for a while until I realized I ate the same thing every day so I just copied over the previous day's entries and changed the values. EFFICIENCY!

`data/food.json`
Contains all the nutritional facts that I've inputted for things I've consumed. Very easy to add new foods, so long as the general structure for new entries are consistent with old format. See `data/template_food.json`

`data/meals.json`
Combined food diary entries from June 2024 to October 2024. Generated by `merge.py`. Had to do this merge so that `trend.py` can do a merged analysis... although technically I guess I could've just scripted it to walk through all the json files in `data/diary/`

`data/estimate_hand.json`
Currently unused, but was going to be for estimating food portions and weights using the hand measurement technique when a scale was unavailable. I haven't had a chance to implement this.

`data/template_food.json`
Template for Food JSON entries. Any new food entries that go in `data/food.json` should be in this format.

`data/template_recipe.json`
Template for a recipe in JSON format. In the dated JSONs in `data/diary`, this is the listed in `foods` key.

`bin/`
Directory containing some helper scripts and classes used by `app.py`

`bin/food_obj.py`
Food class, used to hold food data.

`bin/helpers.py`
Helper scripts used by the app. Only helper script at the moment is `calc_food`, which converts values for food weights relative to the serving size.

`bin/recipe_obj.py`
Recipe class, which combines food nutritional data based on Food objects assigned to it.