/**
 * DictionaryView: Verwaltung des persönlichen Wörterbuchs.
 *
 * Ermöglicht dem Betreuer:
 * - Wörter hinzufügen/entfernen
 * - Kategorien verwalten
 * - Favoriten markieren
 * - Wörterbuch exportieren/importieren
 */

import { useState, useEffect } from 'react';

interface DictEntry {
  word: string;
  category: string;
  usage_count: number;
  is_favorite: boolean;
  notes: string;
}

interface DictionaryViewProps {
  onClose: () => void;
}

const CATEGORY_LABELS: Record<string, string> = {
  allgemein: 'Allgemein',
  personen: 'Personen',
  orte: 'Orte',
  aktivitaeten: 'Aktivitäten',
  medizin: 'Medizin',
  essen_trinken: 'Essen & Trinken',
  gefuehle: 'Gefühle',
  koerper: 'Körper',
  gegenstaende: 'Gegenstände',
};

export function DictionaryView({ onClose }: DictionaryViewProps) {
  const [entries, setEntries] = useState<DictEntry[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [newWord, setNewWord] = useState('');
  const [newCategory, setNewCategory] = useState('allgemein');
  const [newNotes, setNewNotes] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [stats, setStats] = useState<{ total: number; categories: Record<string, number> }>({
    total: 0,
    categories: {},
  });

  // Daten laden
  useEffect(() => {
    loadDictionary();
    loadStats();
  }, [selectedCategory]);

  const loadDictionary = () => {
    const params = new URLSearchParams();
    if (selectedCategory) params.set('category', selectedCategory);
    fetch(`/api/dictionary/words?${params}`)
      .then(r => r.json())
      .then(data => setEntries(data.entries || []))
      .catch(() => {});
  };

  const loadStats = () => {
    fetch('/api/dictionary/stats')
      .then(r => r.json())
      .then(data => setStats(data))
      .catch(() => {});
  };

  const addWord = () => {
    if (!newWord.trim()) return;
    fetch('/api/dictionary/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        word: newWord.trim(),
        category: newCategory,
        notes: newNotes,
      }),
    })
      .then(() => {
        setNewWord('');
        setNewNotes('');
        loadDictionary();
        loadStats();
      });
  };

  const removeWord = (word: string) => {
    fetch('/api/dictionary/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word }),
    })
      .then(() => {
        loadDictionary();
        loadStats();
      });
  };

  const toggleFavorite = (word: string) => {
    fetch('/api/dictionary/favorite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word }),
    })
      .then(() => loadDictionary());
  };

  const filteredEntries = entries.filter(e =>
    !searchTerm || e.word.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full p-6 overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Persönliches Wörterbuch</h2>
        <div className="flex gap-2">
          <a
            href="/api/dictionary/export"
            download
            className="px-3 py-2 bg-white/10 rounded-lg text-sm hover:bg-white/20"
          >
            Exportieren
          </a>
          <button
            onClick={onClose}
            className="px-3 py-2 bg-white/10 rounded-lg text-sm hover:bg-white/20"
          >
            Schließen
          </button>
        </div>
      </div>

      {/* Statistik */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        <div className="bg-[var(--bg-card)] rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-[var(--accent-highlight)]">{stats.total}</div>
          <div className="text-xs text-white/50">Wörter gesamt</div>
        </div>
        <div className="bg-[var(--bg-card)] rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-[var(--accent-selected)]">
            {entries.filter(e => e.is_favorite).length}
          </div>
          <div className="text-xs text-white/50">Favoriten</div>
        </div>
        <div className="bg-[var(--bg-card)] rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-[var(--accent-confirm)]">
            {Object.keys(stats.categories).length}
          </div>
          <div className="text-xs text-white/50">Kategorien</div>
        </div>
        <div className="bg-[var(--bg-card)] rounded-lg p-3 text-center">
          <div className="text-2xl font-bold">
            {entries.reduce((sum, e) => sum + e.usage_count, 0)}
          </div>
          <div className="text-xs text-white/50">Nutzungen</div>
        </div>
      </div>

      <div className="flex gap-4 flex-1 min-h-0">
        {/* Linke Spalte: Kategorien */}
        <div className="w-48 flex-shrink-0">
          <h3 className="text-sm text-white/40 mb-2">Kategorien</h3>
          <div className="space-y-1">
            <button
              onClick={() => setSelectedCategory('')}
              className={`w-full text-left px-3 py-2 rounded text-sm ${
                !selectedCategory ? 'bg-[var(--accent-highlight)]/20 text-[var(--accent-highlight)]' : 'hover:bg-white/10'
              }`}
            >
              Alle ({stats.total})
            </button>
            {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setSelectedCategory(key)}
                className={`w-full text-left px-3 py-2 rounded text-sm ${
                  selectedCategory === key
                    ? 'bg-[var(--accent-highlight)]/20 text-[var(--accent-highlight)]'
                    : 'hover:bg-white/10'
                }`}
              >
                {label} ({stats.categories[key] || 0})
              </button>
            ))}
          </div>
        </div>

        {/* Rechte Spalte: Wörter */}
        <div className="flex-1 flex flex-col min-h-0">
          {/* Suche */}
          <div className="mb-3">
            <input
              type="text"
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              placeholder="Suchen..."
              className="w-full px-3 py-2 bg-[var(--bg-card)] border border-white/10 rounded-lg text-sm"
            />
          </div>

          {/* Wort hinzufügen */}
          <div className="flex gap-2 mb-3">
            <input
              type="text"
              value={newWord}
              onChange={e => setNewWord(e.target.value)}
              placeholder="Neues Wort..."
              className="flex-1 px-3 py-2 bg-[var(--bg-card)] border border-white/10 rounded-lg text-sm"
              onKeyDown={e => e.key === 'Enter' && addWord()}
            />
            <select
              value={newCategory}
              onChange={e => setNewCategory(e.target.value)}
              className="px-2 py-2 bg-[var(--bg-card)] border border-white/10 rounded-lg text-sm"
            >
              {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
            <input
              type="text"
              value={newNotes}
              onChange={e => setNewNotes(e.target.value)}
              placeholder="Notiz (optional)"
              className="w-32 px-3 py-2 bg-[var(--bg-card)] border border-white/10 rounded-lg text-sm"
            />
            <button
              onClick={addWord}
              className="px-4 py-2 bg-[var(--accent-highlight)] text-black rounded-lg text-sm font-bold hover:opacity-90"
            >
              +
            </button>
          </div>

          {/* Wort-Liste */}
          <div className="flex-1 overflow-auto space-y-1">
            {filteredEntries.map((entry) => (
              <div
                key={entry.word}
                className="flex items-center gap-3 px-3 py-2 bg-[var(--bg-card)] rounded-lg group"
              >
                <button
                  onClick={() => toggleFavorite(entry.word)}
                  className={`text-lg ${entry.is_favorite ? 'text-yellow-400' : 'text-white/20 hover:text-yellow-400'}`}
                >
                  ★
                </button>
                <span className="flex-1 font-medium">{entry.word}</span>
                <span className="text-xs text-white/30 px-2 py-0.5 bg-white/5 rounded">
                  {CATEGORY_LABELS[entry.category] || entry.category}
                </span>
                <span className="text-xs text-white/30">{entry.usage_count}×</span>
                {entry.notes && (
                  <span className="text-xs text-white/40 italic">{entry.notes}</span>
                )}
                <button
                  onClick={() => removeWord(entry.word)}
                  className="text-red-400/50 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  ✕
                </button>
              </div>
            ))}
            {filteredEntries.length === 0 && (
              <p className="text-center text-white/30 py-8">
                {searchTerm ? 'Keine Treffer.' : 'Keine Einträge in dieser Kategorie.'}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
