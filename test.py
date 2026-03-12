import json
from collections import Counter

# Load the JSON data
with open("clean_wordlist.json", "r", encoding="utf-8") as file:
    data = json.load(file)

# Extract all words
all_words = [entry["word"] for entry in data]

# Count occurrences
word_counts = Counter(all_words)

# Find duplicates
duplicates = {word: count for word, count in word_counts.items() if count > 1}

# Print results
if duplicates:
    print("Repeated words and their counts:")
    for word, count in duplicates.items():
        print(f"{word}: {count} times")
else:
    print("No repeated words found.")