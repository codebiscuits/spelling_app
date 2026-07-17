# Queue

Bug reports, fixes, and improvement notes waiting to be worked on.
Add items below; delete them when done.

## Improvements

- **Times tables (deferred)** — build as a future standalone practice mode with its
  own progression, disconnected from spelling scores. Each table `y` in `x * y`
  is treated like a word list in an unlock ladder ({2,10} → {2,5,10} → {2,3,5,10}
  → … through all of 2–12), with all unlocked tables forming one weighted pool
  where problems the child struggles with come up more often. (The original
  score-top-up version of this idea was replaced by the spelling top-up feature,
  now implemented, so times tables can't become a way to avoid spellings.)

I have manually tested the mini-games and have lots of things i would like to improve. We need to discuss each of these points until you understand enough to plan them all in detail
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

