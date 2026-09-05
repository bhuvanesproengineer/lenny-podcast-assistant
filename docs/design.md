# Design Document

## Project Title: Lenny Growth Assistant

---

## 1. Design Goals

The primary goal of Lenny Growth Assistant is to help users quickly extract valuable insights from long-form podcast content without overwhelming them with information.

The interface is designed to:

- Minimize cognitive load.
- Prioritize conversation over navigation.
- Surface knowledge quickly.
- Support deep learning through Ship 30 essays.
- Keep generated artifacts separate from chat.
- Create an experience similar to modern AI products such as ChatGPT and Claude.

---

## 2. UI/UX Principles

### Simplicity First

Users should be able to ask a question immediately without navigating multiple screens.

### Knowledge Before Features

The focus is on learning and insight discovery rather than complex controls.

### Conversational Interaction

The primary interaction model is chat-based, allowing users to naturally explore ideas through follow-up questions.

### Progressive Disclosure

Advanced functionality such as Ship 30 essays and artifacts appears only when needed.

### Fast Feedback

Users receive immediate feedback during:

- Retrieval
- Generation
- Artifact creation
- Export operations

---

## 3. Information Architecture

```text
Home Page
│
├── Session Sidebar
│   ├── Previous Conversations
│   └── New Chat
│
├── Chat Interface
│   ├── User Messages
│   ├── Assistant Responses
│   └── Suggested Actions
│
└── Artifact Viewer
    ├── Markdown Preview
    ├── HTML Preview
    └── Export Options
```

---

## 4. Core Screens

### Chat Interface

Purpose:

- Ask product and growth questions.
- Continue conversations.
- Explore podcast knowledge.

Key Elements:

- Chat history
- Message composer
- Session management
- Source-backed responses

---

### Artifact Viewer

Purpose:

- Display generated content separately from chat.

Supported Content:

- Ship 30 essays
- Markdown artifacts
- HTML artifacts

Features:

- Side-by-side rendering
- Scrollable preview
- Export functionality

---

### Session Sidebar

Purpose:

- Organize conversations.

Features:

- Session history
- Session switching
- New conversation creation

---

## 5. Key Interaction States

### Loading State

Displayed when:

- Retrieving transcript chunks.
- Generating responses.
- Creating artifacts.

User Feedback:

- Loading indicators
- Status messages

---

### Success State

Displayed when:

- Response generation completes.
- Artifact generation succeeds.
- Export succeeds.

User Feedback:

- Rendered content
- Success notifications

---

### Empty State

Displayed when:

- No conversation exists.
- No artifact has been generated.

User Feedback:

- Helpful onboarding prompts.
- Example questions.

---

### Error State

Displayed when:

- Retrieval fails.
- Model unavailable.
- Export fails.

User Feedback:

- Human-readable error messages.
- Recovery suggestions.

---

## 6. Responsive Design

### Desktop

Primary experience.

Layout:

- Left Sidebar
- Center Chat
- Right Artifact Viewer

Benefits:

- Simultaneous chat and artifact viewing.

---

### Tablet

Layout:

- Collapsible Sidebar
- Main Chat Area
- Toggle Artifact Viewer

---

### Mobile

Layout:

- Full-screen chat.
- Artifact viewer opens as a separate panel.

Benefits:

- Optimized readability.
- Reduced clutter.

---

## 7. Accessibility Considerations

### Keyboard Navigation

Support:

- Tab navigation
- Enter to submit
- Focus management

### Readability

- Clear typography
- Consistent spacing
- Sufficient contrast ratios

### Screen Readers

Support:

- Semantic HTML
- Accessible labels
- ARIA attributes

### Responsive Text

Content remains readable across:

- Desktop
- Tablet
- Mobile

---

## 8. Design Decisions

### Chat-Centered Experience

Reason:

Users naturally ask questions and learn through conversation.

---

### Dedicated Artifact Viewer

Reason:

Generated essays and documents can become lengthy.

Separating artifacts from chat improves readability and prevents clutter.

---

### Session-Based Architecture

Reason:

Users often ask follow-up questions that depend on prior context.

Maintaining sessions improves continuity.

---

### Markdown and HTML Support

Reason:

The assignment requires artifact generation and rendering.

Supporting both formats enables flexibility for learning content and generated assets.

---

### Safe HTML Rendering

Reason:

Generated HTML should be treated as untrusted content.

Protection includes:

- HTML sanitization
- Restricted script execution
- Sandboxed rendering environment

---

## 9. User Journey

### Knowledge Discovery

User Question
→ Transcript Retrieval
→ Grounded Answer
→ Follow-Up Questions

---

### Content Creation

User Request
→ Ship 30 Skill
→ Essay Generation
→ Artifact Viewer
→ Export

---

### Continuous Learning

User Session
→ Multiple Conversations
→ Knowledge Exploration
→ Personalized Learning