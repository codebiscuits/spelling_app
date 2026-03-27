# Project Requirements
## Tech Stack
I want the code to be understandable by me as much as possible, so that means sticking to pure python, sqlite, html, css, and simple javascript/react. If some parts of the code need to go beyond that, we can discuss it at the time, otherwise lets try and keep it as simple as possible.
## Core Features
- user profiles for each child to allow progress tracking
- Admin access for adding words etc
- Word lists for each school year (specified below)
- Custom word lists
- Mini games as a reward for daily practice
- words can be presented in one of two ways, either displayed and then hidden or played as audio
- Displays score at the end of each test and shows the correct spelling of any they got wrong
- Badges/trophies for progress gamification (one badge and one trophy for each word list, badge for mastering enough of the list to pass, trophy for spelling every word in the list correct)
- Per child dashboard in the admin section
- No distracting customisation options for the child
- Colour palette changes subtly each day to keep things feeling fresh
- Use the previous performance to influence which words get presented, ie choose the words randomly, but if a child spelled a word correctly the last time they attempted it, maybe leave it out of the rotation for a week or two
## Best Practices
- Use **prepared statements** for every query (to prevent SQL injection).
## Database Schema
- users table
	- Id
	- Name
	- Dob
	- Password hash
	- Date created
	- Bool column for each word list to record whether the child has unlocked that list
		- they could start with just the easiest list unlocked or the add user form could allow the admin to select which lists are unlocked
		- New lists should probably be unlocked by mastering previous lists, but should mastered lists be locked to stop the child from just doing the easy option? Maybe the mini games should only appear after the child has attempted a list that they haven’t mastered yet
	- Bool column for each badge and trophy (will need to be able to automatically add new ones of these whenever a new word list is added)
- Words table
	- Word (can be primary key because they will naturally be unique)
	- List id (foreign key, the word list it appears in)
- Word list tables
	- Id
	- Name
- Table for recording every spelling attempt made by every child
	- Id
	- Date and time
	- Child id
	- Word id
	- Correct?
	- Question number (which of the 15 words in that day’s test was it?)
	- Attempt number (was it the first or second attempt of that particular word on that test?)
- Table of final results of each test (this could be recreated from the spelling attempts table but might be easier to store in this form too rather than calculate it from individual attempts)
	- Id
	- Date and time
	- Child id
	- List id
	- Score 
- Table of badges and trophies (this will either need a column to distinguish between the badges and the trophies, or just be two separate tables)
	- Id
	- Name
	- Image url
	- List id
## Design
### Colour Palettes
7 colour palettes, one for each day of the week to keep things feeling fresh. As well as rotating the palettes each day, I could randomly assign the colours within each palette to the various elements so it's never the same scheme.
1. Soft Sky
	- Light Pink → `#FADADD`    
	- Pale Yellow → `#FFF8D6`    
	- Sky Blue → `#B5EAEA`    
	- Mint Green → `#C8E6C9`    
	- Lavender Gray → `#E6E6FA`
2. Candy Pastels
	- Baby Blue → `#A7C7E7`
	- Soft Coral → `#FFB6B9`
	- Pale Lemon → `#FAF3A0`
	- Mint → `#B5EAD7`
	- Lilac → `#C7CEEA`
3. Warm and Cosy
	- Light Peach → `#FFDAB9`
	- Sage Green → `#C8E6C9`
	- Cream Beige → `#FFF5E1`
	- Soft Rose → `#F8C8DC`
	- Taupe Gray → `#E2D6CF`
4. Cool Breeze
	- Powder Blue → `#BFD7ED`
	- Pale Lilac → `#E3DFFD`
	- Soft Aqua → `#CDEDEA`
	- Light Sage → `#D7E5D7`
	- Mist Gray → `#F2F2F2`
5. Garden Pastels
	- Butter Yellow → `#FFF9C4`
	- Fresh Green → `#AED581`
	- Petal Pink → `#F8BBD0`
	- Baby Blue → `#81D4FA`
	- Cloud White → `#FAFAFA`
6. Sunset Glow
	- Peach → `#FFD1BA`
	- Rose Pink → `#F8AFA6`
	- Warm Yellow → `#FFF2B2`
	- Sage → `#B5CDA3`
	- Lavender → `#C7B8EA`
7. Ocean Pastels
	- Aqua Blue → `#AEEEEE`
	- Soft Coral → `#FFCCCC`
	- Seafoam Green → `#C1E1C1`
	- Pale Lavender → `#E6E6FA`
	- Off White → `#FDFDFD`
