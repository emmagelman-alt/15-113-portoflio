# Mosaic-Game
game project for 15-114
I want to build a multiplayer art game. This should be a python file. The concept is a single or multiplayer  player art game in a pixel style where the objective is to recreate client image requests out of simple mosaics. The first screen should be a pixelated landscape scene with the title of the game “mosaic master” and an option for single or multiplayer. If a single player is chosen. The next screen should be  the first person view with a desk, a box of assorted tiles of shapes and colors, and a line of customer npcs in front. The npc walks up to the table and a speech bubble with their image request pops up. A button for accept and a button for skip appear as well. If the active player accepts the request by pressing accept, the worldview shifts so the screen is entirely filled by the table with a canvas, tile pile, shape options, image request, and finish button ( reference Desktop-1.png) 

The user should be able to toggle between shapes by pressing any of the shape buttons at the bottom of the screen which should change the tiles in the pile to only be of variations of that shape and lots of different colors. For example, if i chose a circle i should see lots of different colors and sizes of circle tiles in the pile. The user should be able to drag any of the tiles from the pile onto the canvas to create an arrangement. The tiles should only overlap if double clicked, otherwise they should not overlap. When a user is finished with their composition they hit submit which changes the worldview back to starting but the table displays their finished piece. An API call runs a similarity check between the image request and the composition and the easier the composition is to identify as the image query the higher percentage score out of 100 the user receives. This should take 2-3 seconds. After this, the npc walks away and the next one comes to the front of the line and poses a new randomly generated image request. The images should be of simple objects or scenes. Such as “black dog”, “sunflower”, “sunset on beach” etc. 

If multiplayer is chosen, an option to either join server or create server will appear as buttons. If the create server is selected, the user will see a code popup and a waiting for friend text line to appear. The other user on their own computer will select the join server and then be prompted to enter a code. They will enter the code on the first person’s computer and be connected to the server. Instead of clients, multiplayer will just consist of the mosaic creations type and a random image prompt. There will be a customizable time limit of 30 seconds, 1 minute, 2 minutes, 5 minutes, or 10 minutes. Both players create the mosaic and hit finish before the timer runs out. The worldview will shift to display both mosaics side by side and the players vote on which turned out best. The users can play multiple rounds once voting is over by clicking the next round button or exit by clicking return home button. 

## Running the game (single player)

1. Open Terminal and go to this folder:
   `cd ~/Documents/GitHub/Mosaic-Game`
2. One-time setup:
   `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
3. Play:
   `.venv/bin/python mosaic_master.py`

### Controls
- **Drag** a tile from the pile onto the canvas. Tiles slide to the nearest open spot instead of overlapping.
- **Double-click** a tile on the canvas to let it overlap others (it glows). Double-click again to turn that off.
- **R** rotates the tile under your mouse (Shift+R rotates the other way).
- **Drag a tile off the canvas** to remove it.
- Shape buttons along the bottom switch what's in the pile.
- **Finish** hands your piece to the customer, who scores it 0-100%.

### Status
- Scoring is a **placeholder**: `placeholder_score()` in `mosaic_master.py` rewards canvas coverage, color variety and tile count. It doesn't check whether the picture matches the request yet; the plan is to replace it with an image-similarity API call that returns `(score, comment)`.
- Multiplayer is not built yet.
