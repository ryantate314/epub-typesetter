-- Adds a lettrine drop cap to the first paragraph following each chapter
-- heading. If that paragraph doesn't start with a plain word (e.g. it opens
-- with italics), it's left alone rather than guessed at. Leading quotation
-- marks (common for chapters that open with dialogue) are peeled off and
-- kept as normal-sized text before the drop cap, so the cap itself is
-- always an actual letter.
--
-- Uses the Blocks filter (not Pandoc/top-level only) so this also applies
-- inside Div wrappers -- epub chapter content is often nested in a
-- <div class="chapter">, not sitting at the document's top level.

local LEADING_PUNCTUATION = {
  ["\u{201C}"] = true, -- “
  ["\u{201D}"] = true, -- ”
  ["\u{2018}"] = true, -- ‘
  ["\u{2019}"] = true, -- ’
  ["\u{2014}"] = true, -- —
  ["\""] = true,
  ["'"] = true,
}

local function escape_latex(s)
  return (s:gsub("[{}$&#%%^_~]", function(c)
    if c == "^" then return "\\^{}"
    elseif c == "~" then return "\\~{}"
    else return "\\" .. c end
  end))
end

-- Splits text into (leading punctuation, drop-cap letter, rest of word).
-- Returns nil if the whole token is punctuation (nothing left to cap).
local function split_leading_punctuation(text)
  local len = pandoc.text.len(text)
  local i = 1
  while i <= len and LEADING_PUNCTUATION[pandoc.text.sub(text, i, i)] do
    i = i + 1
  end
  if i > len then
    return nil
  end
  local prefix = i > 1 and pandoc.text.sub(text, 1, i - 1) or ""
  local first = pandoc.text.sub(text, i, i)
  local rest = i < len and pandoc.text.sub(text, i + 1, len) or ""
  return prefix, first, rest
end

function Blocks(blocks)
  local after_header = false
  for _, block in ipairs(blocks) do
    if block.t == "Header" then
      after_header = true
    elseif after_header and block.t == "Para" then
      local inlines = block.content
      if #inlines > 0 and inlines[1].t == "Str" then
        local prefix, first, rest = split_leading_punctuation(inlines[1].text)
        if first then
          local new_inlines = {}
          if prefix ~= "" then
            table.insert(new_inlines, pandoc.Str(prefix))
          end
          table.insert(
            new_inlines,
            pandoc.RawInline(
              "latex",
              "\\lettrine{" .. escape_latex(first) .. "}{" .. escape_latex(rest) .. "}"
            )
          )
          for j = 2, #inlines do
            table.insert(new_inlines, inlines[j])
          end
          block.content = new_inlines
        end
      end
      after_header = false
    else
      after_header = false
    end
  end
  return blocks
end
