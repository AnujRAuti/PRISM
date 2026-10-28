-- Script de inicialização para habilitar extensões
-- Este script será executado automaticamente quando o container for criado

-- Verificar versão do PostgreSQL
SELECT version();

-- Criar extensão PostGIS (compilada manualmente)
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;

-- Criar extensão pgvector (compilada manualmente)
CREATE EXTENSION IF NOT EXISTS vector;

-- Verificar se as extensões foram instaladas corretamente
SELECT 
    extname AS "Extensão",
    extversion AS "Versão",
    extrelocatable AS "Relocável"
FROM pg_extension 
WHERE extname IN ('postgis', 'vector', 'postgis_topology', 'fuzzystrmatch', 'postgis_tiger_geocoder')
ORDER BY extname;

-- Verificar versões específicas das bibliotecas
SELECT PostGIS_Full_Version();

-- Criar uma tabela de exemplo para demonstrar o uso das extensões
CREATE TABLE IF NOT EXISTS exemplo_dados (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100),
    localizacao GEOMETRY(POINT, 4326),
    embedding VECTOR(3),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Inserir alguns dados de exemplo
INSERT INTO exemplo_dados (nome, localizacao, embedding) VALUES 
('São Paulo', ST_SetSRID(ST_MakePoint(-46.6333, -23.5505), 4326), '[0.1, 0.2, 0.3]'::vector),
('Rio de Janeiro', ST_SetSRID(ST_MakePoint(-43.1729, -22.9068), 4326), '[0.4, 0.5, 0.6]'::vector),
('Brasília', ST_SetSRID(ST_MakePoint(-47.8826, -15.7942), 4326), '[0.7, 0.8, 0.9]'::vector);

-- Criar índices para melhor performance
CREATE INDEX IF NOT EXISTS idx_exemplo_localizacao ON exemplo_dados USING GIST (localizacao);
CREATE INDEX IF NOT EXISTS idx_exemplo_embedding ON exemplo_dados USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Exemplo de consulta geoespacial
SELECT 
    nome,
    ST_AsText(localizacao) as coordenadas,
    ST_Distance(
        localizacao, 
        ST_SetSRID(ST_MakePoint(-46.6333, -23.5505), 4326)
    ) as distancia_sp_graus
FROM exemplo_dados
ORDER BY distancia_sp_graus;

-- Exemplo de consulta de similaridade de vetores
SELECT 
    nome,
    embedding <=> '[0.1, 0.2, 0.3]'::vector AS distancia_coseno
FROM exemplo_dados
ORDER BY embedding <=> '[0.1, 0.2, 0.3]'::vector
LIMIT 3;

-- Informações finais
\echo ''
\echo '✅ Extensões PostGIS e pgvector instaladas e configuradas!'
\echo '📍 PostGIS: Dados geoespaciais'
\echo '🔍 pgvector: Busca por similaridade de vetores'
\echo '📊 Tabela de exemplo: exemplo_dados'
\echo ''
