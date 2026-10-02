import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import App from './App';
import { AuthProvider } from './context/AuthContext';

describe('App', () => {
  test('renders the DocQuery heading (login screen when logged out)', async () => {
    render(
      <AuthProvider>
        <App />
      </AuthProvider>
    );
    // No token in localStorage in this test environment, so the app
    // settles on the login screen — which also carries the DocQuery
    // heading, once the initial auth check resolves.
    expect(
      await screen.findByRole('heading', { name: /docquery/i })
    ).toBeInTheDocument();
  });
});
