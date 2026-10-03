// Política de privacidade: o que o Crônica guarda, para quê, quem vê e como pedir para apagar.
import { app, box } from "../ui.js";

export function renderPrivacy() {
  app.innerHTML = `<div class="privacy">${box("Política de privacidade", `
    <p class="muted">Última atualização: outubro de 2026.</p>
    <p>O Crônica é um projeto acadêmico, sem fins lucrativos, mantido por João Victor R. Lisboa, estudante de Sistemas de Informação da UFPA. Esta página explica, em linguagem simples, como os seus dados são tratados, conforme a Lei Geral de Proteção de Dados (LGPD, Lei nº 13.709/2018).</p>

    <h3 class="section-title">O que guardamos</h3>
    <ul>
      <li><b>Conta:</b> nome, e-mail e senha. A senha é guardada embaralhada (com bcrypt): nem quem mantém o site consegue lê-la.</li>
      <li><b>Perfil, se você preencher:</b> foto, instituição, área, cidade, texto "sobre mim", frase, interesses e links.</li>
      <li><b>Seus artigos:</b> os arquivos de cada versão, as mensagens de cada versão, quem salvou e quando.</li>
      <li><b>Convites e organizações</b> de que você participa.</li>
    </ul>
    <p>Não usamos cookies. O navegador guarda só a sua sessão (para você não precisar entrar de novo a cada página) e a cor escolhida para o fundo. O endereço IP é usado por poucos minutos, só na memória do servidor, para limitar tentativas de login; ele não é gravado pelo Crônica.</p>

    <h3 class="section-title">Para que usamos</h3>
    <p>Só para o site funcionar: entrar na sua conta, guardar e mostrar as versões dos seus artigos e permitir escrever em grupo. Não vendemos nem compartilhamos dados com ninguém, não mostramos anúncios e não usamos os seus textos para treinar programas.</p>

    <h3 class="section-title">Quem vê o quê</h3>
    <ul>
      <li>Seus artigos: só você, os coautores que você convidar e os membros da organização em que o artigo estiver.</li>
      <li>Seu perfil (nome, foto, instituição e o que você escreveu nele): só quem escreve com você, participa das mesmas organizações ou trocou convites com você.</li>
      <li>Seu e-mail: ninguém além de você.</li>
    </ul>

    <h3 class="section-title">Onde ficam os dados</h3>
    <p>Em serviços de hospedagem contratados para rodar o site e o banco de dados, que podem ficar fora do Brasil. A conexão com o site é criptografada (HTTPS).</p>

    <h3 class="section-title">Seus direitos</h3>
    <ul>
      <li><b>Ver e corrigir:</b> em "Perfil", você vê e muda os seus dados a qualquer momento.</li>
      <li><b>Levar os dados:</b> em "Perfil", "Baixar meus dados" gera um .zip com o perfil, a foto e os seus artigos.</li>
      <li><b>Apagar:</b> em "Perfil", "Excluir minha conta" apaga a conta e os artigos que você criou. Se você salvou versões em artigos de outras pessoas, elas continuam no histórico desses artigos, mas assinadas como "Conta excluída", sem o seu nome.</li>
    </ul>
    <p>A demonstração não pede dados pessoais e é apagada sozinha em poucas horas.</p>

    <h3 class="section-title">Contato</h3>
    <p>Dúvidas ou pedidos sobre os seus dados: <a href="https://github.com/joaovictor-rl" target="_blank" rel="noopener noreferrer">github.com/joaovictor-rl</a>.</p>
    <p><a href="#/" class="button">Voltar</a></p>
  `)}</div>`;
}
