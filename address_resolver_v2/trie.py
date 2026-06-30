class TrieNode:
    def __init__(self):
        self.children = {}
        self.data = []


class Trie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, word, data):
        if not word:
            return
        node = self.root
        for ch in word:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        node.data.append(data)

    def search_from(self, text, start):
        results = []
        node = self.root
        i = start
        n = len(text)
        while i < n and text[i] in node.children:
            node = node.children[text[i]]
            i += 1
            if node.data:
                results.append((start, i, text[start:i], list(node.data)))
        return results

    def search_all(self, text):
        results = []
        n = len(text)
        for start in range(n):
            results.extend(self.search_from(text, start))
        return results
