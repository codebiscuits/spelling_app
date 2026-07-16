# Queue

Bug reports, fixes, and improvement notes waiting to be worked on.
Add items below; delete them when done.

## Bugs

Discuss each of these before writing an implementation plan
- the unlocked mini-games are available without the child doing a spelling test, this is not how it should work. the child should only be offered the available games upon completion of a spelling test
- the countdown timer occupies the same space on the screen as the mute/unmute button
- the new games are supposed to be unlocked once every 3 starts the child earns, but they are currently unlocking every 1 star

## Improvements

I have manually tested the mini-games and have lots of things i would like to improve. We need to discuss each of these points until you understand enough to plan them all in detail
- pond is very difficult to play, the water ripple simulation is quite extreme, i should do a q&a with claude to work out what's wrong there
- puppet pets has a very low frame-rate, how can we improve rendering performance? maybe just reducing the default number of puppets to 1 would improve things? any other options would be welcome because it would have a big impact on the feel of the game
- mandala maker:
	- the in-game mandala canvas (not the technical html canvas object) should be larger than the viewport so that the user doesn't see the edges as it rotates
	- there should be a way of controlling the brush width, the current setting fills the canvas with white much too quickly
	- also, the color is too 'additive', by which i mean that overlapping points of color add up to white very quickly, so dragging a line almost always results in a mostly white line with just a hint of the color at the edges, the brightness of the colors should be set appropriately so that the brightness spectrum is more evenly distributed
- firefly field needs firefly speed to be slightly faster or enable user control of firefly speed
- splash bath: the constant shaking is too much. maybe change it so that the user can cause the screen shaking by pressing the space bar
- pattern grower/reaction diffusion: left-drag and right-drag do basically the same thing, it would be nice if they each had a distinct effect on the game state
- wrecking yard: 
	- the blocks distort in very unrealistic ways, stretching out into long needle shapes. they should either break into smaller pieces or become smaller in one dimension whilst staying the same in other dimensions
	- the blocks in each tower are stuck together, they don't separate from each other when you hit the tower
	- the initial configuration of blocks is nice, but it would be even better if there were more than one initial state that could be cycled through when the reset button is pressed, or maybe even the initial state could be randomised each time the game starts (as long as there are some structures to demolish)
	- the screen shake effect should be proportional to the mass of the wrecking ball, so maximum shaking only happens when the wrecking ball is at maximum mass
- topple tower: 
	- when blocks collide, their bounce velocity should be very slightly lower (`impact velocity * ~0.9`) than their impact velocity, it seems as though bounce velocity is set to a constant at the moment, but it should be derived from the speed with which the two blocks collided.
	- gravity well feature immediately causes all blocks to fly off-screen and not return, not a very useful game mechanic, needs tweaking
	- screen shaking is too much. it should be somewhat proportional to the amount of action happening in the game world. for example, it could be based on the number of blocks that are currently falling, as a coefficient of the number of falling blocks beyond a certain threshold, up to a certain limit. the game is written in JavaScript, but to explain the calculation i will use python: 
	```Python
	threshold = 5
	limit = 10
	magnitude = num_falling_blocks - threshold
	bounded_magnitude = max(0, min(magnitude, limit))
	screen_shake_coefficient = bounded_magnitude / limit
	```

