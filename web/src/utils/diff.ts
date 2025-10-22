// web/src/utils/diff.ts
// Optional: Install with `npm install diff` and `npm install --save-dev @types/diff`
// This provides a more sophisticated diff view

import * as Diff from 'diff';

export interface DiffBlock {
  type: 'added' | 'removed' | 'unchanged';
  value: string;
  lineNumber?: number;
}

/**
 * Compute a word-level diff between two texts
 */
export function computeWordDiff(oldText: string, newText: string): DiffBlock[] {
  const changes = Diff.diffWords(oldText, newText);
  
  return changes.map(change => ({
    type: change.added ? 'added' : change.removed ? 'removed' : 'unchanged',
    value: change.value,
  }));
}

/**
 * Compute a line-level diff between two texts
 */
export function computeLineDiff(oldText: string, newText: string): DiffBlock[] {
  const changes = Diff.diffLines(oldText, newText);
  
  let lineNumber = 1;
  return changes.map(change => {
    const block: DiffBlock = {
      type: change.added ? 'added' : change.removed ? 'removed' : 'unchanged',
      value: change.value,
      lineNumber: lineNumber,
    };
    
    if (!change.removed) {
      lineNumber += (change.value.match(/\n/g) || []).length;
    }
    
    return block;
  });
}

/**
 * Format diff for display - only shows added/removed content
 */
export function formatDiffForDisplay(oldText: string, newText: string): string {
  const changes = computeLineDiff(oldText, newText);
  
  // Filter to only show changes
  const relevantChanges = changes.filter(c => c.type !== 'unchanged');
  
  if (relevantChanges.length === 0) {
    return '✓ No changes detected - documents are identical';
  }
  
  let output = '';
  
  for (const change of relevantChanges) {
    const lines = change.value.split('\n').filter(l => l.trim().length > 0);
    
    for (const line of lines) {
      if (change.type === 'added') {
        output += `+ ${line}\n`;
      } else if (change.type === 'removed') {
        output += `- ${line}\n`;
      }
    }
  }
  
  return output.trim();
}

/**
 * Get diff statistics
 */
export function getDiffStats(oldText: string, newText: string) {
  const changes = computeLineDiff(oldText, newText);
  
  let added = 0;
  let removed = 0;
  
  for (const change of changes) {
    const lineCount = (change.value.match(/\n/g) || []).length + 1;
    
    if (change.type === 'added') {
      added += lineCount;
    } else if (change.type === 'removed') {
      removed += lineCount;
    }
  }
  
  return { added, removed, modified: changes.filter(c => c.type !== 'unchanged').length };
}

/**
 * Format diff with context (shows unchanged lines around changes)
 */
export function formatDiffWithContext(
  oldText: string, 
  newText: string, 
  contextLines: number = 3
): string {
  const changes = computeLineDiff(oldText, newText);
  
  if (changes.every(c => c.type === 'unchanged')) {
    return '✓ No changes detected - documents are identical';
  }
  
  let output = '';
  let lastWasChange = false;
  
  for (let i = 0; i < changes.length; i++) {
    const change = changes[i];
    const lines = change.value.split('\n').filter(l => l.length > 0);
    
    if (change.type === 'unchanged') {
      // Show context lines before and after changes
      const showStart = lastWasChange && i > 0;
      const showEnd = i < changes.length - 1 && changes[i + 1].type !== 'unchanged';
      
      if (showStart || showEnd) {
        const contextCount = showStart && showEnd ? contextLines * 2 : contextLines;
        const displayLines = showStart 
          ? lines.slice(0, contextLines)
          : lines.slice(-contextLines);
        
        for (const line of displayLines) {
          output += `  ${line}\n`;
        }
        
        if (lines.length > contextLines * 2) {
          output += `  ... (${lines.length - contextLines * 2} unchanged lines)\n`;
        }
      }
      
      lastWasChange = false;
    } else {
      // Show all added/removed lines
      for (const line of lines) {
        if (change.type === 'added') {
          output += `+ ${line}\n`;
        } else if (change.type === 'removed') {
          output += `- ${line}\n`;
        }
      }
      
      lastWasChange = true;
    }
  }
  
  return output.trim();
}

/**
 * Generate a unified diff format
 */
export function generateUnifiedDiff(
  oldText: string, 
  newText: string,
  oldFileName: string = 'original',
  newFileName: string = 'modified'
): string {
  const patch = Diff.createPatch(
    'document',
    oldText,
    newText,
    oldFileName,
    newFileName
  );
  
  return patch;
}