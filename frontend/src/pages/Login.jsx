import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';

export default function Login() {
  const navigate = useNavigate();
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      let response;
      
      if (isLogin) {
        // Login
        response = await api.post('/auth/login', {
          email,
          password,
        });
      } else {
        // Registrar
        response = await api.post('/auth/register', {
          email,
          password,
        });
      }

      // Salvar token
      const token = response.data.access_token;
      localStorage.setItem('access_token', token);
      localStorage.setItem('userEmail', email);

      // Redirecionar para Dashboard
      navigate('/');
    } catch (err) {
      const message = err.response?.data?.detail || 'Erro ao conectar';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-900 via-blue-800 to-purple-900 flex items-center justify-center">
      <div className="w-full max-w-md">
        {/* Logo/Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">PICS</h1>
          <p className="text-blue-100">Personal Image & Content System</p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-lg shadow-xl p-8">
          <h2 className="text-2xl font-bold text-gray-800 mb-6 text-center">
            {isLogin ? 'Fazer Login' : 'Criar Conta'}
          </h2>

          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="seu@email.com"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none bg-white text-gray-900 placeholder-gray-500"
                required
              />
            </div>

            {/* Password */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Senha
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none bg-white text-gray-900 placeholder-gray-500"
                required
              />
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-semibold py-2 rounded-lg transition"
            >
              {loading ? 'Aguardando...' : (isLogin ? 'Login' : 'Registrar')}
            </button>
          </form>

          {/* Toggle Login/Register */}
          <div className="mt-6 text-center">
            <p className="text-gray-600">
              {isLogin ? 'Não tem conta? ' : 'Já tem conta? '}
              <button
                type="button"
                onClick={() => {
                  setIsLogin(!isLogin);
                  setError('');
                }}
                className="text-blue-600 hover:text-blue-700 font-semibold"
              >
                {isLogin ? 'Registrar' : 'Login'}
              </button>
            </p>
          </div>

          {/* Info */}
          <div className="mt-6 p-4 bg-blue-50 rounded-lg text-sm text-gray-700">
            <p className="font-semibold mb-2">🔐 Sua aplicação está segura</p>
            <p>Todas as rotas são protegidas com autenticação JWT.</p>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-8 text-blue-100 text-sm">
          <p>PICS © 2026 - Sistema de Fotos com IA</p>
        </div>
      </div>
    </div>
  );
}
